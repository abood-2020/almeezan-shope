from datetime import date
from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from shop.models import Order, OrderLine, PriceListItem, Product, ProductOption, Trader


def get_active_trader(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    trader = (
        Trader.objects.select_related("user", "price_list__currency")
        .filter(user=user)
        .first()
    )
    if trader is None or not trader.is_active:
        return None
    return trader


def login_trader(request, username, password):
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Invalid credentials.")
    if not user.is_active:
        raise PermissionDenied("This account is inactive.")
    trader = (
        Trader.objects.select_related("user", "price_list__currency")
        .filter(user=user)
        .first()
    )
    if trader is None:
        raise PermissionDenied("No trader profile is linked to this account.")
    if not trader.is_active:
        raise PermissionDenied("This trader account is inactive.")
    login(request, user)
    return trader


def catalog_products(trader=None):
    queryset = Product.objects.select_related("category").prefetch_related(
        "images",
        "colors",
        "sizes",
        "options",
    )
    if trader is not None:
        queryset = queryset.prefetch_related(
            Prefetch(
                "price_list_items",
                queryset=PriceListItem.objects.filter(price_list=trader.price_list),
            )
        )
    return queryset.order_by("id")


def _line_error(index, message):
    raise ValidationError({"items": [f"Item {index + 1}: {message}"]})


def prepare_order_lines(trader, items):
    if not items:
        raise ValidationError({"items": ["Add at least one product."]})
    prepared = []
    for index, item in enumerate(items):
        try:
            product = Product.objects.get(pk=item["product_id"])
        except Product.DoesNotExist:
            _line_error(index, "Unknown product.")
        if not product.available:
            _line_error(index, "This product is unavailable.")
        option = ProductOption.objects.filter(product=product, label=item["option"]).first()
        if option is None:
            _line_error(index, "This option does not belong to the product.")
        if not option.is_available:
            _line_error(index, "This option is unavailable.")
        quantity = item["qty"]
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            _line_error(index, "Quantity must be a positive integer.")
        if quantity < product.min_qty:
            _line_error(index, f"Minimum quantity is {product.min_qty}.")
        unit_price = trader.price_list.price_for(product)
        if unit_price is None:
            _line_error(index, "No price is set for this product on your price list.")
        prepared.append((product, option.label, quantity, unit_price))
    return prepared


def allocate_order_number(day: date) -> str:
    prefix = f"RW-{day.year}-"
    highest = 1000
    numbers = Order.objects.select_for_update().filter(number__startswith=prefix).values_list("number", flat=True)
    for number in numbers:
        suffix = number.removeprefix(prefix)
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1}"


def create_order(trader, note, items):
    prepared = prepare_order_lines(trader, items)
    total = sum((unit_price * quantity for _, _, quantity, unit_price in prepared), Decimal("0"))
    today = timezone.localdate()
    currency = trader.price_list.currency
    for _ in range(3):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    number=allocate_order_number(today),
                    trader=trader,
                    trader_name_ar=trader.name_ar,
                    ordered_on=today,
                    status=Order.Status.REVIEW,
                    currency=currency,
                    currency_symbol=currency.symbol,
                    note=note or "",
                    total=total,
                )
                OrderLine.objects.bulk_create([
                    OrderLine(
                        order=order,
                        product=product,
                        product_code=product.code,
                        product_name_ar=product.name_ar,
                        product_name_en=product.name_en,
                        option_label=label,
                        quantity=quantity,
                        unit_price=unit_price,
                    )
                    for product, label, quantity, unit_price in prepared
                ])
            return Order.objects.prefetch_related("lines").select_related("currency", "trader").get(pk=order.pk)
        except IntegrityError:
            continue
    raise ValidationError("Could not allocate an order number.")
