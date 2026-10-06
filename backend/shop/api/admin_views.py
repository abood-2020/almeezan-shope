from django.contrib.auth import logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shop.api.admin_serializers import (
    CategoryWriteSerializer,
    CurrencyWriteSerializer,
    InvoiceWriteSerializer,
    OrderStatusSerializer,
    PasswordSerializer,
    PriceBulkSerializer,
    PriceListWriteSerializer,
    ProductWriteSerializer,
    SettingsWriteSerializer,
    TraderWriteSerializer,
    admin_invoice_payload,
    admin_order_payload,
    admin_product_payload,
    admin_trader_payload,
    currency_payload,
    price_list_payload,
)
from shop.api.permissions import IsStaffUser
from shop.api.serializers import LoginSerializer, category_payload, settings_payload
from shop.api.views import validation_error
from shop.models import Category, Currency, Invoice, Order, PriceList, Product, ProductColor, ProductImage, Trader
from shop.services import (
    add_product_image,
    catalog_products,
    delete_product_image,
    get_site_settings,
    import_products,
    login_staff,
    replace_price_list_prices,
    save_category,
    save_currency,
    save_invoice,
    save_price_list,
    save_product,
    save_trader,
    set_color_image,
    set_trader_password,
    staff_payload,
    update_order_status,
    update_product_image,
    update_site_settings,
)


class AdminAPIView(APIView):
    permission_classes = [IsStaffUser]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_authenticate_header(self, request):
        return "Session"


def _saved(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except DjangoValidationError as exc:
        validation_error(exc)


class AdminLoginView(AdminAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = login_staff(request, serializer.validated_data["username"], serializer.validated_data["password"])
        return Response({"authenticated": True, "user": staff_payload(user)})


class AdminLogoutView(AdminAPIView):
    def post(self, request):
        logout(request)
        return Response({"authenticated": False})


class AdminMeView(AdminAPIView):
    def get(self, request):
        return Response({"authenticated": True, "user": staff_payload(request.user)})


class AdminProductListView(AdminAPIView):
    def get(self, request):
        return Response([admin_product_payload(product) for product in catalog_products()])

    def post(self, request):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = _saved(save_product, serializer.validated_data)
        return Response(admin_product_payload(product), status=201)


class AdminProductDetailView(AdminAPIView):
    def get(self, request, product_id):
        return Response(admin_product_payload(get_object_or_404(catalog_products(), pk=product_id)))

    def patch(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        serializer = ProductWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = _saved(save_product, serializer.validated_data, product)
        return Response(admin_product_payload(product))


class AdminProductImageListView(AdminAPIView):
    def post(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["An image file is required."]})
        image = _saved(
            add_product_image,
            product,
            upload,
            _flag(request.data.get("is_primary", False)),
            int(request.data.get("sort_order") or 0),
        )
        return Response(_image_payload(image), status=201)


class AdminProductImageDetailView(AdminAPIView):
    def patch(self, request, product_id, image_id):
        image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
        is_primary = _flag(request.data["is_primary"]) if "is_primary" in request.data else None
        sort_order = int(request.data["sort_order"]) if "sort_order" in request.data else None
        image = _saved(update_product_image, image, request.FILES.get("file"), is_primary, sort_order)
        return Response(_image_payload(image))

    def delete(self, request, product_id, image_id):
        image = get_object_or_404(ProductImage, pk=image_id, product_id=product_id)
        delete_product_image(image)
        return Response(status=204)


class AdminProductColorImageView(AdminAPIView):
    def post(self, request, product_id, color_id):
        color = get_object_or_404(ProductColor, pk=color_id, product_id=product_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["An image file is required."]})
        color = _saved(set_color_image, color, upload)
        return Response({"id": color.id, "image": color.image.url})


class AdminCategoryListView(AdminAPIView):
    def get(self, request):
        return Response([category_payload(category) for category in Category.objects.all()])

    def post(self, request):
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = _saved(save_category, serializer.validated_data, None, request.FILES.get("image"))
        return Response(category_payload(category), status=201)


class AdminCategoryDetailView(AdminAPIView):
    def get(self, request, category_id):
        return Response(category_payload(get_object_or_404(Category, pk=category_id)))

    def patch(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        serializer = CategoryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = _saved(save_category, serializer.validated_data, category, request.FILES.get("image"))
        return Response(category_payload(category))


class AdminTraderListView(AdminAPIView):
    def get(self, request):
        traders = Trader.objects.select_related("user", "price_list__currency")
        return Response([admin_trader_payload(trader) for trader in traders])

    def post(self, request):
        serializer = TraderWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trader = _saved(save_trader, serializer.validated_data)
        return Response(admin_trader_payload(trader), status=201)


class AdminTraderDetailView(AdminAPIView):
    def get(self, request, trader_id):
        trader = get_object_or_404(Trader.objects.select_related("user", "price_list__currency"), pk=trader_id)
        return Response(admin_trader_payload(trader))

    def patch(self, request, trader_id):
        trader = get_object_or_404(Trader.objects.select_related("user"), pk=trader_id)
        serializer = TraderWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data.pop("password", None)
        if "id" in data and data["id"] != trader.id:
            raise ValidationError({"id": ["Trader id cannot be changed."]})
        data.pop("id", None)
        trader = _saved(save_trader, data, trader)
        return Response(admin_trader_payload(trader))


class AdminTraderPasswordView(AdminAPIView):
    def post(self, request, trader_id):
        trader = get_object_or_404(Trader.objects.select_related("user"), pk=trader_id)
        serializer = PasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_trader_password(trader, serializer.validated_data["password"])
        return Response({"detail": "Password updated."})


class AdminCurrencyListView(AdminAPIView):
    def get(self, request):
        return Response([currency_payload(currency) for currency in Currency.objects.all()])

    def post(self, request):
        serializer = CurrencyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        currency = _saved(save_currency, serializer.validated_data)
        return Response(currency_payload(currency), status=201)


class AdminCurrencyDetailView(AdminAPIView):
    def get(self, request, code):
        return Response(currency_payload(get_object_or_404(Currency, pk=code.upper())))

    def patch(self, request, code):
        currency = get_object_or_404(Currency, pk=code.upper())
        serializer = CurrencyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        currency = _saved(save_currency, serializer.validated_data, currency)
        return Response(currency_payload(currency))


class AdminPriceListListView(AdminAPIView):
    def get(self, request):
        lists = PriceList.objects.select_related("currency").prefetch_related("items")
        return Response([price_list_payload(price_list) for price_list in lists])

    def post(self, request):
        serializer = PriceListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = _currency_data(serializer.validated_data)
        price_list = _saved(save_price_list, data)
        return Response(price_list_payload(price_list), status=201)


class AdminPriceListDetailView(AdminAPIView):
    def get(self, request, price_list_id):
        price_list = get_object_or_404(PriceList.objects.select_related("currency").prefetch_related("items"), pk=price_list_id)
        return Response(price_list_payload(price_list))

    def patch(self, request, price_list_id):
        price_list = get_object_or_404(PriceList.objects.select_related("currency"), pk=price_list_id)
        serializer = PriceListWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = _currency_data(serializer.validated_data)
        if "id" in data and data["id"] != price_list.id:
            raise ValidationError({"id": ["Price list id cannot be changed."]})
        data.pop("id", None)
        price_list = _saved(save_price_list, data, price_list)
        return Response(price_list_payload(price_list))


class AdminPriceListPricesView(AdminAPIView):
    def put(self, request, price_list_id):
        price_list = get_object_or_404(PriceList.objects.select_related("currency"), pk=price_list_id)
        serializer = PriceBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        price_list = _saved(replace_price_list_prices, price_list, serializer.validated_data["prices"])
        return Response(price_list_payload(price_list))


class AdminOrderListView(AdminAPIView):
    def get(self, request):
        orders = Order.objects.select_related("currency", "trader").prefetch_related("lines")
        status = request.query_params.get("status")
        if status:
            if status not in Order.Status.values:
                raise ValidationError({"status": ["Unsupported status."]})
            orders = orders.filter(status=status)
        query = (request.query_params.get("q") or "").strip()
        if query:
            orders = orders.filter(
                Q(number__icontains=query)
                | Q(trader_name_ar__icontains=query)
                | Q(trader__name_en__icontains=query)
            )
        return Response([admin_order_payload(order) for order in orders])


class AdminOrderDetailView(AdminAPIView):
    def get(self, request, order_number):
        order = get_object_or_404(
            Order.objects.select_related("currency", "trader").prefetch_related("lines"),
            number=order_number,
        )
        return Response(admin_order_payload(order))


class AdminOrderStatusView(AdminAPIView):
    def patch(self, request, order_number):
        order = get_object_or_404(Order.objects.select_related("currency", "trader").prefetch_related("lines"), number=order_number)
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = _saved(update_order_status, order, serializer.validated_data["status"])
        return Response(admin_order_payload(order))


class AdminInvoiceListView(AdminAPIView):
    def get(self, request):
        invoices = Invoice.objects.select_related("trader")
        return Response([admin_invoice_payload(invoice) for invoice in invoices])

    def post(self, request):
        serializer = InvoiceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = _saved(save_invoice, serializer.validated_data, None, request.FILES.get("file"))
        return Response(admin_invoice_payload(invoice), status=201)


class AdminInvoiceDetailView(AdminAPIView):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice.objects.select_related("trader"), number=invoice_id)
        return Response(admin_invoice_payload(invoice))

    def patch(self, request, invoice_id):
        invoice = get_object_or_404(Invoice.objects.select_related("trader"), number=invoice_id)
        serializer = InvoiceWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "number" in request.data and str(request.data["number"]) != invoice.number:
            raise ValidationError({"number": ["Invoice number cannot be changed."]})
        data.pop("number", None)
        invoice = _saved(save_invoice, data, invoice, request.FILES.get("file"))
        return Response(admin_invoice_payload(invoice))


class AdminSettingsView(AdminAPIView):
    def get(self, request):
        return Response(settings_payload(get_site_settings()))

    def patch(self, request):
        serializer = SettingsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting = _saved(update_site_settings, serializer.validated_data["company_whatsapp_number"])
        return Response(settings_payload(setting))


class BulkImportView(AdminAPIView):
    def post(self, request):
        payload = request.data
        rows = payload if isinstance(payload, list) else payload.get("rows")
        if not isinstance(rows, list):
            raise ValidationError({"rows": ["Expected a list of rows."]})
        products = _saved(import_products, rows)
        return Response({"created": len(products), "products": [admin_product_payload(product) for product in products]}, status=201)


def _flag(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _image_payload(image):
    from shop.api.serializers import image_value

    return {
        "id": image.id,
        "url": image_value(image.image, image.image_key),
        "image_key": image.image_key,
        "sort_order": image.sort_order,
        "is_primary": image.is_primary,
    }


def _currency_data(data):
    if "currency_code" in data:
        data = dict(data)
        data["currency"] = data.pop("currency_code")
    return data
