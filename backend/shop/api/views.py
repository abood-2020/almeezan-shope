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
    CartSyncSerializer,
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
from django.db import transaction
from shop.models import CartItem, Category, Invoice, Order, Product, category_descendant_ids
from shop.pricing import PriceChangeRequired, quote_many
from shop.google_auth import GoogleAuthError
from shop.services import (
    authenticate_google,
    catalog_products,
    complete_google_profile,
    create_order,
    default_price_list,
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
            "is_staff": bool(trader.user.is_staff),
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
            "is_staff": bool(trader.user.is_staff),
        })


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(category_payloads(Category.objects.all()))


def _requested_currency(request):
    raw = (request.query_params.get("currency") or "").strip().upper()
    if not raw:
        return None
    if raw not in {"CNY", "USD", "ILS"}:
        return False
    from shop.models import Currency

    currency = Currency.objects.filter(pk=raw).first()
    return currency or False


def _catalog_pricing(user):
    """Public prices use the default list. Only the signed-in trader's own row can discount them."""
    if getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
        return default_price_list(), None
    trader = get_active_trader(user)
    if trader is not None:
        return trader.price_list, trader
    return default_price_list(), None


def _catalog_display(request, public):
    display = _requested_currency(request)
    if display is False or not public:
        return display
    if display is not None:
        return display
    from shop.models import Currency

    return Currency.objects.filter(pk="USD").first() or False


class ProductListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        price_list, trader = _catalog_pricing(request.user)
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
        display = _catalog_display(request, trader is None)
        if display is False:
            return Response({"detail": "Unsupported currency."}, status=400)
        quotes = quote_many(
            price_list, products, display_currency=None if display is None else display.code, trader=trader
        ) if price_list is not None else {}
        return Response([
            product_payload(product, price_list, quotes.get(product.id), display)
            for product in products
        ])


class ProductDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, product_id):
        price_list, trader = _catalog_pricing(request.user)
        product = catalog_products(trader).filter(pk=product_id).first()
        if product is None:
            return Response({"detail": "Not found."}, status=404)
        display = _catalog_display(request, trader is None)
        if display is False:
            return Response({"detail": "Unsupported currency."}, status=400)
        quote = None
        if price_list is not None:
            quote = quote_many(
                price_list, [product], display_currency=None if display is None else display.code, trader=trader
            )[product.id]
        return Response(product_payload(product, price_list, quote, display))


class CurrentPricingView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request):
        trader = get_active_trader(request.user)
        price_list = trader.price_list
        products = list(catalog_products(trader))
        display = _requested_currency(request)
        if display is False:
            return Response({"detail": "Unsupported currency."}, status=400)
        quotes = quote_many(price_list, products, display_currency=None if display is None else display.code, trader=trader)
        shown = display or price_list.currency
        return Response({
            "id": price_list.id,
            "name_ar": price_list.name_ar,
            "name_en": price_list.name_en,
            "currency_code": shown.code,
            "currency_symbol": shown.symbol,
            "list_currency_code": price_list.currency_id,
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
                serializer.validated_data.get("display_currency"),
            )
            CartItem.objects.filter(trader=trader).delete()
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


class CartView(APIView):
    permission_classes = [IsActiveTrader]

    def get(self, request):
        trader = get_active_trader(request.user)
        items = CartItem.objects.filter(trader=trader).select_related("product").prefetch_related("product__images")
        valid_items = []
        for item in items:
            if getattr(item.product, "is_archived", False):
                item.delete()
            else:
                valid_items.append(item)
        return Response({
            "items": [
                {
                    "id": item.product_id,
                    "key": f"{item.product_id}-{item.option}",
                    "option": item.option,
                    "qty": item.quantity,
                    "product_code": item.product.code,
                    "factory_code": getattr(item.product, "factory_code", "") or "",
                    "name_ar": item.product.name_ar,
                    "name_en": item.product.name_en,
                    "min_qty": item.product.min_qty,
                    "available": item.product.available,
                }
                for item in valid_items
            ],
            "count": sum(i.quantity for i in valid_items),
        })

    def put(self, request):
        trader = get_active_trader(request.user)
        serializer = CartSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items_data = serializer.validated_data["items"]
        with transaction.atomic():
            CartItem.objects.filter(trader=trader).delete()
            created_items = []
            for entry in items_data:
                product = Product.objects.filter(pk=entry["product_id"], is_archived=False).first()
                if not product:
                    continue
                qty = max(1, entry["quantity"])
                opt = entry.get("option", "")
                created_items.append(CartItem(trader=trader, product=product, option=opt, quantity=qty))
            if created_items:
                CartItem.objects.bulk_create(created_items)
        return self.get(request)

    def delete(self, request):
        trader = get_active_trader(request.user)
        CartItem.objects.filter(trader=trader).delete()
        return Response({"items": [], "count": 0})


class CartMergeView(APIView):
    permission_classes = [IsActiveTrader]

    def post(self, request):
        trader = get_active_trader(request.user)
        serializer = CartSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest_items = serializer.validated_data["items"]

        with transaction.atomic():
            existing = {
                (item.product_id, item.option): item
                for item in CartItem.objects.filter(trader=trader).select_related("product")
            }
            for entry in guest_items:
                product_id = entry["product_id"]
                option = entry.get("option", "")
                qty = max(1, entry["quantity"])
                key = (product_id, option)
                if key in existing:
                    item = existing[key]
                    item.quantity = max(item.quantity, qty)
                    item.save(update_fields=["quantity", "updated_at"])
                else:
                    product = Product.objects.filter(pk=product_id, is_archived=False).first()
                    if product:
                        created = CartItem.objects.create(
                            trader=trader,
                            product=product,
                            option=option,
                            quantity=max(product.min_qty, qty),
                        )
                        existing[key] = created

        return CartView().get(request)
