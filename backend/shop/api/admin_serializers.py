from decimal import Decimal

from rest_framework import serializers

from shop.api.serializers import image_value, invoice_payload, money, product_payload, trader_payload
from shop.models import Category, Currency, PriceList, Product, Trader


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
    base_price_usd = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    original_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False
    )
    original_currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False
    )
    base_currency_code = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), source="base_currency", required=False
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
                "unit_ar",
                "unit_en",
                "min_qty",
                "available",
            ):
                self.fields[name].required = True

    def validate(self, attrs):
        has_original = "original_price" in attrs or "original_currency" in attrs
        if has_original and ("original_price" not in attrs or "original_currency" not in attrs):
            raise serializers.ValidationError({"original_price": "Enter both the original price and its currency."})
        if "original_currency" in attrs and attrs["original_currency"].code not in {"CNY", "USD", "ILS"}:
            raise serializers.ValidationError({"original_currency": "Choose CNY, USD or ILS."})
        if not self.partial and "original_price" not in attrs and "base_price_ils" not in attrs:
            raise serializers.ValidationError({"original_price": "Enter an original price."})
        return attrs


class ParentIdField(serializers.Field):
    def to_internal_value(self, data):
        if data in (None, ""):
            return None
        try:
            category_id = int(data)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Choose a valid parent category.")
        if not Category.objects.filter(pk=category_id).exists():
            raise serializers.ValidationError("Choose a valid parent category.")
        return category_id


class CategoryWriteSerializer(serializers.Serializer):
    name_ar = serializers.CharField(max_length=120)
    name_en = serializers.CharField(max_length=120)
    image_key = serializers.CharField(required=False, allow_blank=True)
    parent_id = ParentIdField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)

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
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    country = serializers.CharField(required=False, allow_blank=True, max_length=80)
    city = serializers.CharField(required=False, allow_blank=True, max_length=80)
    category_discounts = serializers.ListField(child=serializers.DictField(), required=False)
    password = serializers.CharField(required=False, write_only=True, trim_whitespace=False)

    def validate_phone(self, value):
        from shop.content import normalize_phone

        return normalize_phone(value, "phone")

    def validate_country(self, value):
        from shop.content import plain

        return plain(value, "country", 80).strip()

    def validate_city(self, value):
        from shop.content import plain

        return plain(value, "city", 80).strip()

    def validate_category_discounts(self, rows):
        cleaned = []
        for row in rows:
            if "category_id" not in row or "discount_percent" not in row:
                raise serializers.ValidationError("Each discount needs a category and a percentage.")
            try:
                category = Category.objects.get(pk=row["category_id"])
            except (Category.DoesNotExist, TypeError, ValueError) as exc:
                raise serializers.ValidationError("Choose an existing category.") from exc
            cleaned.append({"category": category, "discount_percent": row["discount_percent"]})
        return cleaned

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
    pricing_mode = serializers.ChoiceField(choices=["legacy", "rule_based"], required=False)
    default_discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    is_default = serializers.BooleanField(required=False)
    discount_scope = serializers.ChoiceField(choices=["all", "categories"], required=False)
    scope_category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="scope_categories", many=True, required=False
    )

    def validate(self, attrs):
        if self.partial and "pricing_mode" in self.initial_data:
            raise serializers.ValidationError({
                "pricing_mode": "Confirm the pricing mode change before it is applied.",
            })
        return attrs

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


class PricingModeSerializer(serializers.Serializer):
    pricing_mode = serializers.ChoiceField(choices=["legacy", "rule_based"])
    confirm = serializers.BooleanField(required=False, default=False)


class DiscountRuleSerializer(serializers.Serializer):
    category_id = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), source="category", required=False)
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source="product", required=False)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    is_active = serializers.BooleanField(required=False)


class ExchangeRateWriteSerializer(serializers.Serializer):
    source = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.all(), required=False)
    target = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.all(), required=False)
    rate = serializers.DecimalField(max_digits=18, decimal_places=8, required=False)
    is_active = serializers.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.partial:
            for name in ("source", "target", "rate"):
                self.fields[name].required = True


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
    company_whatsapp_number = serializers.CharField(allow_blank=True, required=False, max_length=20)
    name_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    name_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    tagline_ar = serializers.CharField(required=False, allow_blank=True, max_length=160)
    tagline_en = serializers.CharField(required=False, allow_blank=True, max_length=160)
    header_caption_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    header_caption_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    logo_alt_ar = serializers.CharField(required=False, allow_blank=True, max_length=120)
    logo_alt_en = serializers.CharField(required=False, allow_blank=True, max_length=120)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    email = serializers.CharField(required=False, allow_blank=True, max_length=254)
    address_ar = serializers.CharField(required=False, allow_blank=True, max_length=240)
    address_en = serializers.CharField(required=False, allow_blank=True, max_length=240)
    instagram_url = serializers.CharField(required=False, allow_blank=True, max_length=200)
    facebook_url = serializers.CharField(required=False, allow_blank=True, max_length=200)
    social_links = serializers.ListField(child=serializers.DictField(), required=False)
    seo_title_ar = serializers.CharField(required=False, allow_blank=True, max_length=120)
    seo_title_en = serializers.CharField(required=False, allow_blank=True, max_length=120)
    seo_description_ar = serializers.CharField(required=False, allow_blank=True)
    seo_description_en = serializers.CharField(required=False, allow_blank=True)
    hero_video_url = serializers.CharField(required=False, allow_blank=True, max_length=200)
    footer_explore_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_explore_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_account_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_account_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    copyright_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    copyright_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_note_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_note_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_place_ar = serializers.CharField(required=False, allow_blank=True, max_length=80)
    footer_place_en = serializers.CharField(required=False, allow_blank=True, max_length=80)
    nav_labels = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=80), required=False)


class FaqWriteSerializer(serializers.Serializer):
    question_ar = serializers.CharField(required=False, allow_blank=True, max_length=240)
    question_en = serializers.CharField(required=False, allow_blank=True, max_length=240)
    answer_ar = serializers.CharField(required=False, allow_blank=True)
    answer_en = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False, min_value=0)


def admin_product_payload(product):
    data = product_payload(product)
    data["is_archived"] = getattr(product, "is_archived", False)
    data["base_price_ils"] = money(product.base_price_ils)
    data["base_price_usd"] = money(product.base_price_usd)
    data["base_currency"] = product.base_currency_id
    data["original_price"] = money(product.original_price)
    data["original_currency"] = product.original_currency_id
    data["price_review_required"] = product.price_review_required
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
    from shop.pricing import quote_many

    explicit = {item.product_id: item.price for item in price_list.items.all()}
    products = list(Product.objects.select_related("category", "base_currency").order_by("id"))
    required = {product.id for product in products}
    rule_based = price_list.pricing_mode == "rule_based"
    quotes = quote_many(price_list, products) if rule_based else {}
    if rule_based:
        complete = bool(products) and all(quote.available for quote in quotes.values())
    else:
        complete = price_list.currency_id == "ILS" or set(explicit) == required
    return {
        "id": price_list.id,
        "name_ar": price_list.name_ar,
        "name_en": price_list.name_en,
        "currency_code": price_list.currency_id,
        "currency_symbol": price_list.currency.symbol,
        "is_active": price_list.is_active,
        "pricing_mode": price_list.pricing_mode,
        "default_discount_percent": f"{price_list.default_discount_percent:.2f}",
        "discount_scope": price_list.discount_scope,
        "scope_category_ids": [category.id for category in price_list.scope_categories.all()],
        "is_default": price_list.is_default,
        "complete": complete,
        "prices": [
            {"product_id": product_id, "price": money(price)}
            for product_id, price in sorted(explicit.items())
        ],
        "category_rules": [
            {
                "id": rule.id,
                "category_id": rule.category_id,
                "discount_percent": f"{rule.discount_percent:.2f}",
                "is_active": rule.is_active,
            }
            for rule in price_list.category_rules.all()
        ],
        "product_rules": [
            {
                "id": rule.id,
                "product_id": rule.product_id,
                "discount_percent": f"{rule.discount_percent:.2f}",
                "is_active": rule.is_active,
            }
            for rule in price_list.product_rules.all()
        ],
        "quotes": [
            {
                "product_id": product.id,
                "base_price": money(quotes[product.id].base_price),
                "base_currency": quotes[product.id].base_currency,
                "exchange_rate": None,
                "discount_percent": None if quotes[product.id].discount_percent is None else f"{quotes[product.id].discount_percent:.2f}",
                "rule_source": quotes[product.id].source,
                "category_id": quotes[product.id].category_id,
                "calculated_price": money(quotes[product.id].calculated),
                "overridden": quotes[product.id].overridden,
                "price": money(quotes[product.id].unit_price) if quotes[product.id].available else None,
                "currency_code": price_list.currency_id,
                "available": quotes[product.id].available,
                "error": quotes[product.id].error,
            }
            for product in products
        ] if rule_based else [],
    }


def exchange_rate_payload(rate):
    return {
        "id": rate.id,
        "source": rate.source_id,
        "target": rate.target_id,
        "rate": f"{rate.rate:.8f}",
        "is_active": rate.is_active,
        "updated_at": rate.updated_at.isoformat(),
    }


def admin_order_payload(order):
    from shop.api.serializers import OrderSerializer

    data = OrderSerializer(order).data
    data["trader_id"] = order.trader_id
    return data


def admin_invoice_payload(invoice):
    return invoice_payload(invoice)


def admin_trader_payload(trader):
    payload = trader_payload(trader)
    payload["is_staff"] = bool(trader.user.is_staff)
    return payload
