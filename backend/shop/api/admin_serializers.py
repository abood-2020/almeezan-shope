from decimal import Decimal

from rest_framework import serializers

from shop.api.serializers import image_value, invoice_payload, money, product_payload, trader_payload
from shop.models import Category, Currency, PriceList, Trader


class ColorWriteSerializer(serializers.Serializer):
    name_ar = serializers.CharField(max_length=80)
    name_en = serializers.CharField(max_length=80)
    hex = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$")
    image_key = serializers.CharField(required=False, allow_blank=True, default="")


class ProductWriteSerializer(serializers.Serializer):
    name_ar = serializers.CharField(max_length=200, required=False)
    name_en = serializers.CharField(max_length=200, required=False)
    code = serializers.CharField(max_length=64, required=False)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", required=False
    )
    base_price_ils = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )
    unit_ar = serializers.CharField(max_length=40, required=False)
    unit_en = serializers.CharField(max_length=40, required=False)
    min_qty = serializers.IntegerField(min_value=1, required=False)
    available = serializers.BooleanField(required=False)
    description_ar = serializers.CharField(required=False, allow_blank=True)
    description_en = serializers.CharField(required=False, allow_blank=True)
    badge = serializers.CharField(max_length=40, required=False, allow_blank=True)
    image_key = serializers.CharField(required=False, allow_blank=True)
    gallery = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    colors = ColorWriteSerializer(many=True, required=False)
    sizes = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    options = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    unavailable_variants = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in (
                "name_ar",
                "name_en",
                "code",
                "category_id",
                "base_price_ils",
                "unit_ar",
                "unit_en",
                "min_qty",
                "available",
            ):
                self.fields[name].required = True


class CategoryWriteSerializer(serializers.Serializer):
    name_ar = serializers.CharField(max_length=120)
    name_en = serializers.CharField(max_length=120)
    image_key = serializers.CharField(required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.partial:
            for field in self.fields.values():
                field.required = False


class TraderWriteSerializer(serializers.Serializer):
    id = serializers.SlugField(max_length=32, required=False)
    name_ar = serializers.CharField(max_length=160, required=False)
    name_en = serializers.CharField(max_length=160, required=False)
    username = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    price_list_id = serializers.PrimaryKeyRelatedField(
        queryset=PriceList.objects.all(), source="price_list", required=False
    )
    active = serializers.BooleanField(required=False)
    password = serializers.CharField(required=False, write_only=True, trim_whitespace=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in ("id", "name_ar", "name_en", "username", "price_list_id", "active"):
                self.fields[name].required = True


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)


class CurrencyWriteSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Za-z]{3}$", required=False)
    name = serializers.CharField(max_length=80, required=False)
    symbol = serializers.CharField(max_length=8, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in ("code", "name", "symbol"):
                self.fields[name].required = True

    def validate_code(self, value):
        return value.upper()


class PriceListWriteSerializer(serializers.Serializer):
    id = serializers.SlugField(max_length=32, required=False)
    name_ar = serializers.CharField(max_length=120, required=False)
    name_en = serializers.CharField(max_length=120, required=False)
    currency_code = serializers.CharField(max_length=3, required=False)
    is_active = serializers.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in ("id", "name_ar", "name_en", "currency_code"):
                self.fields[name].required = True

    def validate_currency_code(self, value):
        code = value.strip().upper()
        try:
            return Currency.objects.get(pk=code)
        except Currency.DoesNotExist as exc:
            raise serializers.ValidationError("Unknown currency.") from exc


class PriceRowSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))


class PriceBulkSerializer(serializers.Serializer):
    prices = PriceRowSerializer(many=True)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["review", "confirmed", "complete", "cancelled"])


class InvoiceWriteSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=32, required=False)
    trader_id = serializers.PrimaryKeyRelatedField(queryset=Trader.objects.all(), source="trader", required=False)
    date = serializers.DateField(source="issued_on", required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in ("number", "trader_id", "date", "amount"):
                self.fields[name].required = True


class SettingsWriteSerializer(serializers.Serializer):
    company_whatsapp_number = serializers.CharField(allow_blank=True)


def admin_product_payload(product):
    data = product_payload(product)
    data["base_price_ils"] = money(product.base_price_ils)
    data["images"] = [
        {
            "id": image.id,
            "url": image_value(image.image, image.image_key),
            "image_key": image.image_key,
            "sort_order": image.sort_order,
            "is_primary": image.is_primary,
        }
        for image in product.images.all()
    ]
    data["colors"] = [
        {
            "id": color.id,
            "name_ar": color.name_ar,
            "name_en": color.name_en,
            "hex": color.hex_code,
            "image": image_value(color.image, color.image_key),
        }
        for color in product.colors.all()
    ]
    return data


def currency_payload(currency):
    return {"code": currency.code, "name": currency.name, "symbol": currency.symbol}


def price_list_payload(price_list):
    from shop.models import Product

    explicit = {item.product_id: item.price for item in price_list.items.all()}
    required = set(Product.objects.values_list("id", flat=True))
    return {
        "id": price_list.id,
        "name_ar": price_list.name_ar,
        "name_en": price_list.name_en,
        "currency_code": price_list.currency_id,
        "currency_symbol": price_list.currency.symbol,
        "is_active": price_list.is_active,
        "complete": price_list.currency_id == "ILS" or set(explicit) == required,
        "prices": [
            {"product_id": product_id, "price": money(price)}
            for product_id, price in sorted(explicit.items())
        ],
    }


def admin_order_payload(order):
    from shop.api.serializers import OrderSerializer

    data = OrderSerializer(order).data
    data["trader_id"] = order.trader_id
    return data


def admin_invoice_payload(invoice):
    return invoice_payload(invoice)


def admin_trader_payload(trader):
    return trader_payload(trader)
