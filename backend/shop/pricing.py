"""Central price quotations. Money uses Decimal; percentages are not stacked.

A discount list prices each product in its own currency. A stored list item is a
manual final price and stays fixed until it is removed. Legacy lists keep the
prices already saved on them. Exchange rates and older percentage rules are not
applied.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from shop.models import Category, PriceList


BASE_CURRENCY = "ILS"
HUNDRED = Decimal("100")


class PriceChangeRequired(Exception):
    def __init__(self, items):
        self.items = items


@dataclass(frozen=True)
class PriceQuote:
    available: bool
    unit_price: Decimal | None
    base_price: Decimal | None
    base_currency: str
    exchange_rate: Decimal | None
    discount_percent: Decimal | None
    source: str
    category_id: int | None = None
    error: str = ""
    calculated: Decimal | None = None
    overridden: bool = False


def money_places(currency) -> int:
    places = getattr(currency, "decimal_places", 2)
    return 2 if places is None else int(places)


def quantize_money(amount: Decimal, places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-places)
    return amount.quantize(quantum, rounding=ROUND_HALF_UP)


def parse_discount(value) -> Decimal:
    amount = Decimal(str(value))
    if amount < 0 or amount > 100:
        raise ValidationError({"discount_percent": "Discount must be between 0 and 100."})
    return amount.quantize(Decimal("0.01"))


def unit_price(price_list, product):
    return quote_many(price_list, [product])[product.id].unit_price


def quote_many(price_list, products, mode=None):
    products = list(products)
    mode = mode or price_list.pricing_mode
    if mode == PriceList.PricingMode.LEGACY:
        return {product.id: _legacy_quote(price_list, product, _legacy_prices(price_list)) for product in products}
    return _rule_quotes(price_list, products)


def _legacy_prices(price_list):
    prefetched = getattr(price_list, "_prefetched_objects_cache", {}).get("items")
    rows = prefetched if prefetched is not None else price_list.items.all()
    return {item.product_id: item.price for item in rows}


def _legacy_quote(price_list, product, prices):
    base_currency = getattr(product, "base_currency_id", None) or BASE_CURRENCY
    base_price = product.base_price_ils
    if product.id in prices:
        return PriceQuote(
            True,
            prices[product.id],
            base_price,
            base_currency,
            None,
            None,
            "legacy",
        )
    if price_list.currency_id == BASE_CURRENCY and base_currency == BASE_CURRENCY:
        return PriceQuote(True, base_price, base_price, base_currency, None, None, "legacy")
    return PriceQuote(False, None, base_price, base_currency, None, None, "unavailable", error="missing_price")


def _rule_quotes(price_list, products):
    overrides = _legacy_prices(price_list)
    scope = _discount_scope_ids(price_list)
    target = price_list.currency_id
    places = money_places(price_list.currency)
    discount = price_list.default_discount_percent
    return {
        product.id: _simple_quote(product, overrides, scope, target, places, discount)
        for product in products
    }


def _discount_scope_ids(price_list):
    """None means every product. A set is the selected categories plus descendants."""
    if getattr(price_list, "discount_scope", PriceList.DiscountScope.ALL) != PriceList.DiscountScope.CATEGORIES:
        return None
    selected = [category.id for category in price_list.scope_categories.all()]
    children = {}
    for parent_id, child_id in Category.objects.exclude(parent_id=None).values_list("parent_id", "id"):
        children.setdefault(parent_id, []).append(child_id)
    found = set()
    stack = list(selected)
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, ()))
    return found


def _currency_base(product, currency_code):
    if currency_code == "ILS":
        return product.base_price_ils
    if currency_code == "USD":
        return product.base_price_usd
    return None


def _simple_quote(product, overrides, scope, target, places, discount):
    base = _currency_base(product, target)
    in_scope = scope is None or product.category_id in scope
    applied = discount if in_scope else Decimal("0")
    calculated = None if base is None else quantize_money(base * (HUNDRED - applied) / HUNDRED, places)
    if product.id in overrides:
        return PriceQuote(
            True,
            overrides[product.id],
            base,
            target,
            None,
            None,
            "override",
            calculated=calculated,
            overridden=True,
        )
    if base is None:
        return PriceQuote(
            False,
            None,
            None,
            target,
            None,
            None,
            "unavailable",
            error="missing_price",
        )
    return PriceQuote(
        True,
        calculated,
        base,
        target,
        None,
        applied,
        "discount" if in_scope else "base",
        product.category_id if in_scope else None,
        calculated=calculated,
    )


def quote_payload(quote: PriceQuote, currency_code: str):
    places = 2
    return {
        "available": quote.available,
        "price": _format(quote.unit_price, places) if quote.available else None,
        "calculated_price": _format(quote.calculated, places),
        "overridden": quote.overridden,
        "base_price": _format(quote.base_price, places),
        "base_currency": quote.base_currency,
        "exchange_rate": None,
        "discount_percent": None if quote.discount_percent is None else f"{quote.discount_percent:.2f}",
        "rule_source": quote.source,
        "category_id": quote.category_id,
        "currency_code": currency_code,
        "error": quote.error,
    }


def _format(value, places):
    if value is None:
        return None
    return f"{value:.{places}f}"


def compare_expected_price(expected, quote: PriceQuote):
    if expected is None or not quote.available or quote.unit_price is None:
        return True
    shown = Decimal(str(expected)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    current = quote.unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return shown == current
