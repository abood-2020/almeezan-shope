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
    category_payload,
    invoice_payload,
    money,
    product_payload,
    settings_payload,
    trader_payload,
)
from shop.models import Category, Invoice, Order
from shop.services import catalog_products, create_order, get_active_trader, get_site_settings, login_trader


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
            return Response({"authenticated": False, "trader": None})
        return Response({"authenticated": True, "trader": trader_payload(trader)})


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = Category.objects.order_by("id")
        return Response([category_payload(category) for category in categories])


class ProductListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        trader = get_active_trader(request.user)
        price_list = trader.price_list if trader else None
        products = catalog_products(trader)
        return Response([product_payload(product, price_list) for product in products])


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
        return Response({
            "id": price_list.id,
            "name_ar": price_list.name_ar,
            "name_en": price_list.name_en,
            "currency_code": price_list.currency_id,
            "currency_symbol": price_list.currency.symbol,
            "prices": [
                {"product_id": product.id, "price": money(price_list.price_for(product))}
                for product in catalog_products(trader)
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
            )
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
        return Response(settings_payload(get_site_settings()))
