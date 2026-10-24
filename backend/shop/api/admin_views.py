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
    DiscountRuleSerializer,
    ExchangeRateWriteSerializer,
    InvoiceWriteSerializer,
    OrderStatusSerializer,
    PasswordSerializer,
    PriceBulkSerializer,
    PriceListWriteSerializer,
    PricingModeSerializer,
    ProductWriteSerializer,
    FaqWriteSerializer,
    SettingsWriteSerializer,
    TraderWriteSerializer,
    admin_invoice_payload,
    admin_order_payload,
    admin_product_payload,
    admin_trader_payload,
    currency_payload,
    exchange_rate_payload,
    price_list_payload,
)
from shop.api.permissions import IsStaffUser
from shop.api.serializers import LoginSerializer, category_payload, category_payloads, settings_payload
from shop.api.views import validation_error
from shop.content import reorder_faqs, save_faq, update_pages, update_sections
from shop.exports import export_language, invoice_workbook, order_workbook, xlsx_response
from shop.models import (
    Category,
    Currency,
    ExchangeRate,
    FaqItem,
    Invoice,
    Order,
    PriceList,
    PriceListCategoryRule,
    PriceListProductRule,
    Product,
    ProductColor,
    ProductImage,
    Trader,
)
from shop.services import (
    add_product_image,
    catalog_products,
    delete_product_image,
    get_site_settings,
    import_products,
    AdminAccessError,
    change_trader_admin,
    login_staff,
    replace_price_list_prices,
    save_category,
    save_category_rule,
    save_currency,
    save_exchange_rate,
    save_invoice,
    save_price_list,
    save_product_rule,
    set_pricing_mode,
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
        return Response(category_payloads(Category.objects.all()))

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


def _trader_access_response(request, trader, grant):
    try:
        trader, changed = change_trader_admin(request.user, trader, grant)
    except AdminAccessError as exc:
        return Response({"code": exc.code, "detail": exc.detail}, status=400)
    return Response(
        {
            "trader": admin_trader_payload(trader),
            "is_staff": bool(trader.user.is_staff),
            "changed": changed,
            "self": request.user.pk == trader.user_id,
        }
    )


class AdminTraderPromoteView(AdminAPIView):
    def post(self, request, trader_id):
        trader = get_object_or_404(Trader.objects.select_related("user", "price_list__currency"), pk=trader_id)
        return _trader_access_response(request, trader, True)


class AdminTraderRevokeView(AdminAPIView):
    def post(self, request, trader_id):
        trader = get_object_or_404(Trader.objects.select_related("user", "price_list__currency"), pk=trader_id)
        return _trader_access_response(request, trader, False)


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
        lists = PriceList.objects.select_related("currency").prefetch_related("items", "scope_categories", "category_rules", "product_rules")
        return Response([price_list_payload(price_list) for price_list in lists])

    def post(self, request):
        serializer = PriceListWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = _currency_data(serializer.validated_data)
        price_list = _saved(save_price_list, data)
        return Response(price_list_payload(price_list), status=201)


class AdminPriceListDetailView(AdminAPIView):
    def get(self, request, price_list_id):
        price_list = get_object_or_404(
            PriceList.objects.select_related("currency").prefetch_related("items", "scope_categories", "category_rules", "product_rules"),
            pk=price_list_id,
        )
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
        response = Response(settings_payload(get_site_settings(), include_inactive_faqs=True))
        response["Cache-Control"] = "no-store"
        return response

    def patch(self, request):
        serializer = SettingsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting = _saved(update_site_settings, serializer.validated_data, request.FILES)
        response = Response(settings_payload(setting, include_inactive_faqs=True))
        response["Cache-Control"] = "no-store"
        return response


class AdminOrderExcelView(AdminAPIView):
    def get(self, request, order_number):
        order = get_object_or_404(
            Order.objects.select_related("currency", "trader").prefetch_related("lines"),
            number=order_number,
        )
        return xlsx_response(
            order_workbook(order, export_language(request), get_site_settings()),
            f"Order_{order.number}.xlsx",
        )


class AdminInvoiceExcelView(AdminAPIView):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice.objects.select_related("trader"), number=invoice_id)
        return xlsx_response(
            invoice_workbook(invoice, export_language(request), get_site_settings()),
            f"Invoice_{invoice.number}.xlsx",
        )


class AdminContentSectionsView(AdminAPIView):
    def patch(self, request):
        payload = _saved(update_sections, request.data if isinstance(request.data, list) else request.data.get("sections"))
        response = Response(payload)
        response["Cache-Control"] = "no-store"
        return response


class AdminContentPagesView(AdminAPIView):
    def patch(self, request):
        payload = _saved(update_pages, request.data if isinstance(request.data, list) else request.data.get("pages"))
        response = Response(payload)
        response["Cache-Control"] = "no-store"
        return response


class AdminFaqListView(AdminAPIView):
    def post(self, request):
        serializer = FaqWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _saved(save_faq, serializer.validated_data, None)
        response = Response(settings_payload(get_site_settings(), include_inactive_faqs=True), status=201)
        response["Cache-Control"] = "no-store"
        return response


class AdminFaqDetailView(AdminAPIView):
    def patch(self, request, faq_id):
        item = get_object_or_404(FaqItem, pk=faq_id)
        serializer = FaqWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        _saved(save_faq, serializer.validated_data, item)
        response = Response(settings_payload(get_site_settings(), include_inactive_faqs=True))
        response["Cache-Control"] = "no-store"
        return response

    def delete(self, request, faq_id):
        item = get_object_or_404(FaqItem, pk=faq_id)
        item.delete()
        response = Response(settings_payload(get_site_settings(), include_inactive_faqs=True))
        response["Cache-Control"] = "no-store"
        return response


class AdminFaqOrderView(AdminAPIView):
    def put(self, request):
        payload = _saved(reorder_faqs, request.data.get("ids"))
        response = Response(payload)
        response["Cache-Control"] = "no-store"
        return response


def _category_map(value):
    import json
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError({"category_map": ["Category mapping must be an object."]}) from exc
    if not isinstance(value, dict):
        raise ValidationError({"category_map": ["Category mapping must be an object."]})
    return value


class BulkImportView(AdminAPIView):
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is not None:
            from shop.excel_images import read_import_workbook
            rows, embedded = read_import_workbook(upload)
            lang = request.data.get("lang", "ar")
            products = _saved(import_products, rows, lang, _category_map(request.data.get("category_map")), embedded)
            return Response({"created": len(products), "products": [admin_product_payload(product) for product in products]}, status=201)
        payload = request.data
        if isinstance(payload, list):
            rows = payload
            lang = "ar"
            category_map = None
        else:
            rows = payload.get("rows")
            lang = payload.get("lang", "ar")
            category_map = _category_map(payload.get("category_map"))
        if not isinstance(rows, list):
            raise ValidationError({"rows": ["Expected a list of rows."]})
        products = _saved(import_products, rows, lang, category_map)
        return Response({"created": len(products), "products": [admin_product_payload(product) for product in products]}, status=201)


class ImportPreviewView(AdminAPIView):
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Choose a workbook."]})
        from shop.excel_images import preview_embedded_images
        return Response(preview_embedded_images(upload))


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


class AdminPriceListModeView(AdminAPIView):
    def post(self, request, price_list_id):
        price_list = get_object_or_404(PriceList.objects.select_related("currency"), pk=price_list_id)
        serializer = PricingModeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _saved(
            set_pricing_mode,
            price_list,
            serializer.validated_data["pricing_mode"],
            serializer.validated_data["confirm"],
        )
        if isinstance(result, dict):
            return Response(result)
        return Response(price_list_payload(result))


class AdminCategoryRuleListView(AdminAPIView):
    def post(self, request, price_list_id):
        price_list = get_object_or_404(PriceList, pk=price_list_id)
        serializer = DiscountRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "category" not in serializer.validated_data:
            raise ValidationError({"category_id": ["Choose a category."]})
        if "discount_percent" not in serializer.validated_data:
            raise ValidationError({"discount_percent": ["Enter a discount percentage."]})
        rule = _saved(save_category_rule, price_list, serializer.validated_data)
        return Response(price_list_payload(_price_list(rule.price_list_id)), status=201)


class AdminCategoryRuleDetailView(AdminAPIView):
    def patch(self, request, price_list_id, rule_id):
        rule = get_object_or_404(PriceListCategoryRule, pk=rule_id, price_list_id=price_list_id)
        serializer = DiscountRuleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "discount_percent" not in data:
            data["discount_percent"] = rule.discount_percent
        rule = _saved(save_category_rule, rule.price_list, data, rule)
        return Response(price_list_payload(_price_list(rule.price_list_id)))

    def delete(self, request, price_list_id, rule_id):
        rule = get_object_or_404(PriceListCategoryRule, pk=rule_id, price_list_id=price_list_id)
        rule.delete()
        return Response(price_list_payload(_price_list(price_list_id)))


class AdminProductRuleListView(AdminAPIView):
    def post(self, request, price_list_id):
        price_list = get_object_or_404(PriceList, pk=price_list_id)
        serializer = DiscountRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "product" not in serializer.validated_data:
            raise ValidationError({"product_id": ["Choose a product."]})
        if "discount_percent" not in serializer.validated_data:
            raise ValidationError({"discount_percent": ["Enter a discount percentage."]})
        rule = _saved(save_product_rule, price_list, serializer.validated_data)
        return Response(price_list_payload(_price_list(rule.price_list_id)), status=201)


class AdminProductRuleDetailView(AdminAPIView):
    def patch(self, request, price_list_id, rule_id):
        rule = get_object_or_404(PriceListProductRule, pk=rule_id, price_list_id=price_list_id)
        serializer = DiscountRuleSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "discount_percent" not in data:
            data["discount_percent"] = rule.discount_percent
        rule = _saved(save_product_rule, rule.price_list, data, rule)
        return Response(price_list_payload(_price_list(rule.price_list_id)))

    def delete(self, request, price_list_id, rule_id):
        rule = get_object_or_404(PriceListProductRule, pk=rule_id, price_list_id=price_list_id)
        rule.delete()
        return Response(price_list_payload(_price_list(price_list_id)))


class AdminExchangeRateListView(AdminAPIView):
    def get(self, request):
        rates = ExchangeRate.objects.select_related("source", "target")
        return Response([exchange_rate_payload(rate) for rate in rates])

    def post(self, request):
        serializer = ExchangeRateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rate = _saved(save_exchange_rate, serializer.validated_data)
        return Response(exchange_rate_payload(rate), status=201)


class AdminExchangeRateDetailView(AdminAPIView):
    def patch(self, request, rate_id):
        rate = get_object_or_404(ExchangeRate, pk=rate_id)
        serializer = ExchangeRateWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rate = _saved(save_exchange_rate, serializer.validated_data, rate)
        return Response(exchange_rate_payload(rate))

    def delete(self, request, rate_id):
        rate = get_object_or_404(ExchangeRate, pk=rate_id)
        rate.delete()
        return Response(status=204)


def _price_list(price_list_id):
    return PriceList.objects.select_related("currency").prefetch_related(
        "items", "category_rules", "product_rules"
    ).get(pk=price_list_id)


def _currency_data(data):
    if "currency_code" in data:
        data = dict(data)
        data["currency"] = data.pop("currency_code")
    return data


class AdminFxSnapshotView(AdminAPIView):
    def get(self, request):
        from decimal import Decimal, ROUND_HALF_UP

        from shop.fx import convert_amount, current_snapshot, ensure_store_currencies, snapshot_payload, snapshot_rates

        ensure_store_currencies()
        payload = snapshot_payload()
        amount = request.query_params.get("amount")
        currency = (request.query_params.get("currency") or "").upper()
        if amount not in (None, "") or currency:
            rates = snapshot_rates(current_snapshot())
            if currency not in {"CNY", "USD", "ILS"}:
                raise ValidationError({"currency": ["Choose CNY, USD or ILS."]})
            try:
                original = Decimal(str(amount))
            except Exception as exc:
                raise ValidationError({"amount": ["Enter an original price."]}) from exc
            if original < 0:
                raise ValidationError({"amount": ["Enter an original price of zero or more."]})
            converted = {}
            if rates is None:
                payload["preview_error"] = "missing_exchange_rate"
            else:
                for code in ("CNY", "USD", "ILS"):
                    value, _factor = convert_amount(original, currency, code, rates)
                    converted[code] = f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
            payload["preview"] = {"original_currency": currency, "original_price": f"{original:.2f}", "prices": converted}
        return Response(payload)


class AdminFxHistoryView(AdminAPIView):
    def get(self, request):
        from datetime import date

        from shop.fx import FxError, observation_history
        from shop.models import RateObservation

        def parse_date(field):
            raw = request.query_params.get(field)
            if raw in (None, ""):
                return None
            try:
                return date.fromisoformat(raw)
            except ValueError as exc:
                raise ValidationError({field: ["Enter a date as YYYY-MM-DD."]}) from exc

        start = parse_date("from") or date(2026, 1, 1)
        latest = RateObservation.objects.order_by("-provider_date").values_list("provider_date", flat=True).first()
        end = parse_date("to") or latest or date.today()
        exact = parse_date("date")
        if start > end:
            raise ValidationError({"from": ["From date cannot be after to date."]})
        raw_page = request.query_params.get("page") or "1"
        try:
            page = int(raw_page)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page": ["Enter a page number."]}) from exc
        try:
            history = observation_history(start=start, end=end, exact=exact, page=page)
        except FxError as exc:
            raise ValidationError({"page": ["That page is outside the result set."]}) from exc
        return Response({
            "count": history["count"],
            "page": history["page"],
            "page_size": history["page_size"],
            "pages": history["pages"],
            "from": history["start"].isoformat(),
            "to": history["end"].isoformat(),
            "results": [
                {
                    "date": row.provider_date.isoformat(),
                    "usd_cny": f"{row.cny_per_usd:.8f}",
                    "usd_ils": f"{row.ils_per_usd:.8f}",
                    "provider": "Frankfurter" if row.provider == "frankfurter" else row.provider,
                    "fetched_at": row.fetched_at.isoformat(),
                }
                for row in history["results"]
            ],
        })


class AdminFxRefreshView(AdminAPIView):
    def post(self, request):
        from shop.fx import refresh_exchange_rates, snapshot_payload

        result = refresh_exchange_rates()
        payload = snapshot_payload(result["snapshot"])
        payload["refreshed"] = result["ok"]
        payload["error"] = result["error"]
        status = 200 if result["ok"] else 503
        return Response(payload, status=status)
