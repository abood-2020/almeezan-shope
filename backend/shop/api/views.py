from django.contrib.auth import logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shop.api.permissions import IsActiveTrader
from shop.api.serializers import (
    LoginSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    category_payloads,
    invoice_payload,
    money,
    product_payload,
    settings_payload,
    trader_payload,
)
from shop.exports import export_language, invoice_workbook, order_workbook, xlsx_response
from shop.models import Category, Invoice, Order, category_descendant_ids
from shop.pricing import PriceChangeRequired, quote_many
from shop.google_auth import GoogleAuthError
from shop.services import (
    authenticate_google,
    catalog_products,
    complete_google_profile,
    create_order,
    get_active_trader,
    get_site_settings,
    google_profile_required,
    login_trader,
)


def validation_error(exc):
    if hasattr(exc, "error_dict"):
        detail = {key: value for key, value in exc.message_dict.items()}
        raise ValidationError(detail)
    raise ValidationError(exc.messages)


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        return "Session"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trader = login_trader(request, serializer.validated_data["username"], serializer.validated_data["password"])
        return Response({"authenticated": True, "trader": trader_payload(trader)})


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        return "Session"

    def post(self, request):
        credential = request.data.get("credential") if isinstance(request.data, dict) else None
        try:
            trader, profile_required = authenticate_google(request, credential)
        except GoogleAuthError as exc:
            return Response({"code": exc.code}, status=exc.status)
        return Response({
            "authenticated": True,
            "trader": trader_payload(trader),
            "profile_required": profile_required,
        })


class GoogleProfileView(APIView):
    permission_classes = [IsActiveTrader]

    def post(self, request):
        trader = get_active_trader(request.user)
        try:
            trader = complete_google_profile(trader, request.data)
        except DjangoValidationError as exc:
            validation_error(exc)
        return Response({
            "authenticated": True,
            "trader": trader_payload(trader),
            "profile_required": False,
        })


class LogoutView(APIView):
    permission_classes = [IsActiveTrader]

    def post(self, request):
        logout(request)
        return Response({"authenticated": False})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        trader = get_active_trader(request.user)
        if trader is None:
            return Response({"authenticated": False, "trader": None, "profile_required": False})
        return Response({
            "authenticated": True,
            "trader": trader_payload(trader),
            "profile_required": google_profile_required(trader),
        })


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(category_payloads(Category.objects.all()))


class ProductListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        trader = get_active_trader(request.user)
        price_list = trader.price_list if trader else None
        products = list(catalog_products(trader))
        selected = request.query_params.get("category")
        if selected not in (None, ""):
            try:
                category_id = int(selected)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid category."}, status=400)
            if not Category.objects.filter(pk=category_id).exists():
                return Response({"detail": "Not found."}, status=404)
            allowed = set(category_descendant_ids(category_id))
            products = [product for product in products if product.category_id in allowed]
        quotes = quote_many(price_list, products) if price_list is not None else {}
        return Response([
            product_payload(product, price_list, quotes.get(product.id))
            for product in products
        ])


class ProductDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, product_id):
        trader = get_active_trader(request.user)
        price_list = trader.price_list if trader else None
        product = catalog_products(trader).filter(pk=product_id).first()
        if product is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(product_payload(product, price_list))


class CurrentPricingView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request):
        trader = get_active_trader(request.user)
        price_list = trader.price_list
        products = list(catalog_products(trader))
        quotes = quote_many(price_list, products)
        return Response({
            "id": price_list.id,
            "name_ar": price_list.name_ar,
            "name_en": price_list.name_en,
            "currency_code": price_list.currency_id,
            "currency_symbol": price_list.currency.symbol,
            "pricing_mode": price_list.pricing_mode,
            "default_discount_percent": f"{price_list.default_discount_percent:.2f}",
            "prices": [
                {
                    "product_id": product.id,
                    "price": money(quotes[product.id].unit_price) if quotes[product.id].available else None,
                    "base_price": money(quotes[product.id].base_price),
                    "base_currency": quotes[product.id].base_currency,
                    "discount_percent": None if quotes[product.id].discount_percent is None else f"{quotes[product.id].discount_percent:.2f}",
                    "exchange_rate": None if quotes[product.id].exchange_rate is None else f"{quotes[product.id].exchange_rate:.8f}",
                    "rule_source": quotes[product.id].source,
                    "error": quotes[product.id].error,
                }
                for product in products
            ],
        })


class OrderListCreateView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request):
        trader = get_active_trader(request.user)
        orders = Order.objects.filter(trader=trader).prefetch_related("lines").select_related("currency")
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trader = get_active_trader(request.user)
        try:
            order = create_order(
                trader,
                serializer.validated_data.get("note", ""),
                serializer.validated_data["items"],
                serializer.validated_data.get("acknowledge_price_changes", False),
            )
        except PriceChangeRequired as exc:
            return Response({"price_changed": True, "items": exc.items}, status=409)
        except DjangoValidationError as exc:
            validation_error(exc)
        return Response(OrderSerializer(order).data, status=201)


class OrderDetailView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request, order_number):
        trader = get_active_trader(request.user)
        order = (
            Order.objects.filter(trader=trader, number=order_number)
            .prefetch_related("lines")
            .select_related("currency")
            .first()
        )
        if order is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(OrderSerializer(order).data)


class InvoiceListView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request):
        trader = get_active_trader(request.user)
        invoices = Invoice.objects.filter(trader=trader).select_related("trader")
        return Response([invoice_payload(invoice) for invoice in invoices])


class InvoiceDetailView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request, invoice_id):
        trader = get_active_trader(request.user)
        invoice = Invoice.objects.filter(trader=trader, number=invoice_id).select_related("trader").first()
        if invoice is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(invoice_payload(invoice))


class PublicSettingsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        response = Response(settings_payload(get_site_settings()))
        response["Cache-Control"] = "no-store"
        return response


class OrderExcelView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request, order_number):
        trader = get_active_trader(request.user)
        order = (
            Order.objects.filter(trader=trader, number=order_number)
            .prefetch_related("lines")
            .select_related("currency", "trader")
            .first()
        )
        if order is None:
            return Response({"detail": "Not found."}, status=404)
        return xlsx_response(order_workbook(order, export_language(request), get_site_settings()), f"Order_{order.number}.xlsx")


class InvoiceExcelView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request, invoice_id):
        trader = get_active_trader(request.user)
        invoice = Invoice.objects.filter(trader=trader, number=invoice_id).select_related("trader").first()
        if invoice is None:
            return Response({"detail": "Not found."}, status=404)
        return xlsx_response(invoice_workbook(invoice, export_language(request), get_site_settings()), f"Invoice_{invoice.number}.xlsx")
