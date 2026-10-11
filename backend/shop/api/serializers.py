from rest_framework import serializers

from shop.models import Category, Order, OrderLine


def image_value(file_field, image_key):
    if file_field:
        return file_field.url
    return image_key or ""


def money(value):
    if value is None:
        return None
    return f"{value:.2f}"


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    option = serializers.CharField()
    qty = serializers.IntegerField(min_value=1)
    expected_unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )


class OrderCreateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
    acknowledge_price_changes = serializers.BooleanField(required=False, default=False)
    items = serializers.ListField(child=OrderItemInputSerializer(), allow_empty=False)


class OrderLineSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(source="product_code")
    name_ar = serializers.CharField(source="product_name_ar")
    name_en = serializers.CharField(source="product_name_en")
    option = serializers.CharField(source="option_label")
    qty = serializers.IntegerField(source="quantity")
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    line_total = serializers.SerializerMethodField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    base_currency = serializers.CharField()
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, allow_null=True)

    class Meta:
        model = OrderLine
        fields = [
            "product_id",
            "code",
            "name_ar",
            "name_en",
            "option",
            "qty",
            "unit_price",
            "line_total",
            "base_price",
            "base_currency",
            "discount_percent",
            "exchange_rate",
        ]

    def get_line_total(self, line):
        if line.line_total is not None:
            return money(line.line_total)
        return money(line.unit_price * line.quantity)


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.CharField()
    date = serializers.DateField(source="ordered_on")
    currency_code = serializers.CharField(source="currency_id")
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    items = OrderLineSerializer(source="lines", many=True)

    class Meta:
        model = Order
        fields = [
            "number",
            "date",
            "status",
            "trader_name_ar",
            "note",
            "currency_code",
            "currency_symbol",
            "total",
            "items",
        ]


def trader_payload(trader):
    price_list = trader.price_list
    return {
        "id": trader.id,
        "username": trader.user.username,
        "name_ar": trader.name_ar,
        "name_en": trader.name_en,
        "email": trader.user.email,
        "active": trader.is_active,
        "price_list": {
            "id": price_list.id,
            "name_ar": price_list.name_ar,
            "name_en": price_list.name_en,
            "currency_code": price_list.currency_id,
            "currency_symbol": price_list.currency.symbol,
        },
    }


def invoice_payload(invoice):
    if invoice.file:
        file_url = invoice.file.url
    else:
        file_url = invoice.file_ref or ""
    return {
        "id": invoice.number,
        "number": invoice.number,
        "trader_id": invoice.trader_id,
        "date": invoice.issued_on.isoformat(),
        "amount": money(invoice.amount),
        "file_url": file_url,
        "file_name": invoice.file_name,
    }


def settings_payload(setting, include_inactive_faqs=False):
    from shop.content import content_payload

    del setting
    return content_payload(include_inactive_faqs=include_inactive_faqs)


def category_payloads(categories):
    parent_of = {category.id: category.parent_id for category in categories}
    children_of = {}
    for category in categories:
        children_of.setdefault(category.parent_id, []).append(category.id)
    levels = {}

    def level(category_id):
        if category_id in levels:
            return levels[category_id]
        parent_id = parent_of.get(category_id)
        levels[category_id] = 1 if not parent_id else level(parent_id) + 1
        return levels[category_id]

    return [
        {
            "id": category.id,
            "name_ar": category.name_ar,
            "name_en": category.name_en,
            "image": image_value(category.image, category.image_key),
            "parent_id": category.parent_id,
            "level": level(category.id),
            "sort_order": category.sort_order,
            "children": children_of.get(category.id, []),
        }
        for category in categories
    ]


def category_payload(category):
    depth = 1
    current = category.parent_id
    seen = {category.id}
    while current and current not in seen:
        seen.add(current)
        depth += 1
        current = Category.objects.filter(pk=current).values_list("parent_id", flat=True).first()
    return {
        "id": category.id,
        "name_ar": category.name_ar,
        "name_en": category.name_en,
        "image": image_value(category.image, category.image_key),
        "parent_id": category.parent_id,
        "level": depth,
        "sort_order": category.sort_order,
        "children": list(category.children.order_by("sort_order", "id").values_list("id", flat=True)),
    }


def product_payload(product, price_list=None, quote=None):
    images = list(product.images.all())
    primary = next((image for image in images if image.is_primary), None)
    if primary is None and images:
        primary = images[0]
    data = {
        "id": product.id,
        "name_ar": product.name_ar,
        "name_en": product.name_en,
        "code": product.code,
        "category_id": product.category_id,
        "unit_ar": product.unit_ar,
        "unit_en": product.unit_en,
        "min_qty": product.min_qty,
        "available": product.available,
        "description_ar": product.description_ar,
        "description_en": product.description_en,
        "badge": product.badge,
        "image": image_value(primary.image, primary.image_key) if primary else "",
        "gallery": [image_value(image.image, image.image_key) for image in images],
        "colors": [
            {
                "name_ar": color.name_ar,
                "name_en": color.name_en,
                "hex": color.hex_code,
                "image": image_value(color.image, color.image_key),
            }
            for color in product.colors.all()
        ],
        "sizes": [size.value for size in product.sizes.all()],
        "options": [option.label for option in product.options.all()],
        "unavailable_variants": [option.label for option in product.options.all() if not option.is_available],
    }
    if price_list is not None:
        if quote is None:
            from shop.pricing import quote_many

            quote = quote_many(price_list, [product])[product.id]
        data["price"] = money(quote.unit_price) if quote.available else None
        data["currency_code"] = price_list.currency_id
        data["currency_symbol"] = price_list.currency.symbol
        if not quote.available:
            data["price_error"] = quote.error or "missing_price"
    return data
