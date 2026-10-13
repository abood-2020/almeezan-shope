"""Central price quotations. Money uses Decimal; percentages are not stacked.

A discount list prices each product in its own currency. A stored list item is a
manual final price and stays fixed until it is removed. Legacy lists keep the
prices already saved on them. Exchange rates and older percentage rules are not
applied.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from shop.fx import checkout_allowed, conversion_factor, current_snapshot, rate_status, snapshot_rates
from shop.models import Category, PriceList, TraderCategoryDiscount


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
    original_price: Decimal | None = None
    original_currency: str = ""
    pricing_note: str = ""
    checkout_allowed: bool = True
    rate_status: str = ""


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


def quote_many(price_list, products, mode=None, display_currency=None, trader=None):
    """Quote every product from one rate snapshot.

    A product with an original price is converted from that fixed amount.
    Products that still have two independently entered base prices keep the
    existing list-currency behavior until an administrator chooses an original.
    """
    products = list(products)
    mode = mode or price_list.pricing_mode
    if mode == PriceList.PricingMode.LEGACY:
        quotes = {product.id: _legacy_quote(price_list, product, _legacy_prices(price_list)) for product in products}
    else:
        quotes = _rule_quotes(price_list, products)
    display = (display_currency or price_list.currency_id or BASE_CURRENCY).upper()
    return _present_quotes(price_list, products, quotes, display, trader, mode)


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


def _present_quotes(price_list, products, quotes, display, trader, mode):
    snapshot = current_snapshot()
    rates = snapshot_rates(snapshot)
    status = rate_status(snapshot)
    parents = dict(Category.objects.exclude(parent_id=None).values_list("id", "parent_id"))
    trader_rules = {}
    if trader is not None:
        trader_rules = {
            row.category_id: row.discount_percent
            for row in TraderCategoryDiscount.objects.filter(trader=trader)
        }
    scope = None if mode == PriceList.PricingMode.LEGACY else _discount_scope_ids(price_list)
    overrides = _legacy_prices(price_list)
    places = 2
    presented = {}
    for product in products:
        if mode != PriceList.PricingMode.LEGACY and _has_original(product):
            quote = _original_quote(product, price_list, display, rates, snapshot, status, scope, overrides, places)
        else:
            quote = quotes[product.id]
            source_currency = price_list.currency_id
            if display != source_currency:
                quote = _convert_finished_quote(quote, source_currency, display, rates, snapshot, status, places)
        if mode != PriceList.PricingMode.LEGACY and trader is not None and quote.available and not quote.overridden and quote.base_price is not None:
            quote = _apply_trader_discount(quote, product, trader_rules, parents, places)
        presented[product.id] = quote
    return presented


def _has_original(product):
    return product.original_price is not None and product.original_currency_id in {"CNY", "USD", "ILS"}


def _ancestor_chain(category_id, parents):
    chain = []
    seen = set()
    current = category_id
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = parents.get(current)
    return chain


def _rate_context(source, target, rates, snapshot, status):
    if source == target:
        return Decimal("1"), "", True
    if rates is None:
        return None, "missing_exchange_rate", False
    try:
        factor = conversion_factor(rates, source, target)
    except Exception:
        return None, "missing_exchange_rate", False
    allowed = checkout_allowed(status)
    return factor, "" if allowed or status == "blocked" else "missing_exchange_rate", allowed or status == "blocked"


def _original_quote(product, price_list, display, rates, snapshot, status, scope, overrides, places):
    amount = product.original_price
    source = product.original_currency_id
    if product.id in overrides:
        factor, error, allowed = _rate_context(price_list.currency_id, display, rates, snapshot, status)
        if factor is None:
            return PriceQuote(False, None, amount, source, None, None, "unavailable", error=error or "missing_exchange_rate", original_price=amount, original_currency=source, checkout_allowed=False, rate_status=status)
        unit = quantize_money(overrides[product.id] * factor, places)
        return PriceQuote(
            True, unit, amount, source, None if factor == 1 else factor, None, "override",
            calculated=None, overridden=True, original_price=amount, original_currency=source,
            pricing_note="manual price", checkout_allowed=factor == 1 or status != "blocked", rate_status=status,
        )
    in_scope = scope is None or product.category_id in scope
    percent = price_list.default_discount_percent if in_scope else Decimal("0")
    factor, error, allowed = _rate_context(source, display, rates, snapshot, status)
    if factor is None:
        return PriceQuote(
            False, None, amount, source, None, None, "unavailable",
            error=error or "missing_exchange_rate", original_price=amount, original_currency=source,
            checkout_allowed=False, rate_status=status,
        )
    raw = amount * factor
    unit = quantize_money(raw * (HUNDRED - percent) / HUNDRED, places)
    base = quantize_money(raw, places)
    note = "price list discount" if in_scope and percent else "original price"
    return PriceQuote(
        True, unit, base, display, None if factor == 1 else factor, percent,
        "discount" if in_scope and percent else "base",
        product.category_id if in_scope and percent else None,
        calculated=unit, original_price=amount, original_currency=source,
        pricing_note=note, checkout_allowed=factor == 1 or status != "blocked", rate_status=status,
    )


def _convert_finished_quote(quote, source, target, rates, snapshot, status, places):
    factor, error, allowed = _rate_context(source, target, rates, snapshot, status)
    if factor is None or not quote.available or quote.unit_price is None:
        return PriceQuote(
            False, None, quote.base_price, quote.base_currency, None, quote.discount_percent, "unavailable",
            error=error or quote.error or "missing_exchange_rate", checkout_allowed=False, rate_status=status,
        )
    return PriceQuote(
        True,
        quantize_money(quote.unit_price * factor, places),
        None if quote.base_price is None else quantize_money(quote.base_price * factor, places),
        target,
        None if factor == 1 else factor,
        quote.discount_percent,
        quote.source,
        quote.category_id,
        calculated=None if quote.calculated is None else quantize_money(quote.calculated * factor, places),
        overridden=quote.overridden,
        original_price=quote.original_price,
        original_currency=quote.original_currency,
        pricing_note=quote.pricing_note,
        checkout_allowed=factor == 1 or status != "blocked",
        rate_status=status,
    )


def _apply_trader_discount(quote, product, rules, parents, places):
    match = None
    matched_category = None
    for category_id in _ancestor_chain(product.category_id, parents):
        if category_id in rules:
            match = rules[category_id]
            matched_category = category_id
            break
    if match is None or quote.base_price is None:
        return quote
    unit = quantize_money(quote.base_price * (HUNDRED - match) / HUNDRED, places)
    return PriceQuote(
        True, unit, quote.base_price, quote.base_currency, quote.exchange_rate, match, "trader_category",
        matched_category, calculated=unit, overridden=False, original_price=quote.original_price,
        original_currency=quote.original_currency, pricing_note="trader category discount",
        checkout_allowed=quote.checkout_allowed, rate_status=quote.rate_status,
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
        "exchange_rate": None if quote.exchange_rate is None else f"{quote.exchange_rate:.8f}",
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
