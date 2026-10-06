from rest_framework import serializers

from shop.models import Order, OrderLine


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


class OrderCreateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
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

    class Meta:
        model = OrderLine
        fields = ["product_id", "code", "name_ar", "name_en", "option", "qty", "unit_price", "line_total"]

    def get_line_total(self, line):
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


def settings_payload(setting):
    return {"company_whatsapp_number": setting.company_whatsapp_number}


def category_payload(category):
    return {
        "id": category.id,
        "name_ar": category.name_ar,
        "name_en": category.name_en,
        "image": image_value(category.image, category.image_key),
    }


def product_payload(product, price_list=None):
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
        data["price"] = money(price_list.price_for(product))
        data["currency_code"] = price_list.currency_id
        data["currency_symbol"] = price_list.currency.symbol
    return data
