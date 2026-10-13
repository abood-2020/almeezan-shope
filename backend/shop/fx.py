"""USD-normalized exchange rates from Frankfurter. Storefront requests never call the provider."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from shop.models import Currency, FxRefreshLock, RateSnapshot, RateSnapshotLine


log = logging.getLogger(__name__)

STORE_CURRENCIES = ("CNY", "USD", "ILS")
RATE_QUANTUM = Decimal("0.00000001")
PROVIDER = "frankfurter"


class FxError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def ensure_store_currencies():
    rows = (
        ("CNY", "Chinese Yuan Renminbi", "¥"),
        ("USD", "US Dollar", "$"),
        ("ILS", "Israeli Shekel", "₪"),
    )
    for code, name, symbol in rows:
        Currency.objects.get_or_create(
            code=code,
            defaults={"name": name, "symbol": symbol, "decimal_places": 2},
        )


def current_snapshot():
    return (
        RateSnapshot.objects.filter(is_current=True)
        .prefetch_related("lines")
        .order_by("-provider_date", "-fetched_at")
        .first()
    )


def snapshot_rates(snapshot):
    if snapshot is None:
        return None
    rates = {line.currency_id: line.usd_rate for line in snapshot.lines.all()}
    if not set(STORE_CURRENCIES).issubset(rates):
        return None
    return rates


def rate_age_days(snapshot, today=None):
    today = today or timezone.localdate()
    age = (today - snapshot.provider_date).days
    return 0 if age < 0 else age


def rate_status(snapshot, today=None):
    """current, stale, blocked, or missing. Age uses the provider date, so a Friday rate is still fresh on Monday."""
    if snapshot is None or snapshot_rates(snapshot) is None:
        return "missing"
    age = rate_age_days(snapshot, today)
    if age > int(getattr(settings, "FX_CHECKOUT_MAX_AGE_DAYS", 10)):
        return "blocked"
    if age > int(getattr(settings, "FX_STALE_DAYS", 5)):
        return "stale"
    return "current"


def checkout_allowed(status):
    return status in {"current", "stale"}


def conversion_factor(rates, source, target):
    if source == target:
        return Decimal("1")
    if not rates or source not in rates or target not in rates:
        raise FxError("missing_exchange_rate")
    source_rate = rates[source]
    target_rate = rates[target]
    if source_rate <= 0 or target_rate <= 0:
        raise FxError("missing_exchange_rate")
    return (target_rate / source_rate).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def convert_amount(amount, source, target, rates):
    factor = conversion_factor(rates, source, target)
    return amount * factor, factor


def parse_frankfurter(payload):
    if not isinstance(payload, dict):
        raise FxError("invalid_response")
    base = str(payload.get("base") or "").upper()
    rates = payload.get("rates")
    raw_date = payload.get("date")
    if base != "USD" or not isinstance(rates, dict) or not raw_date:
        raise FxError("invalid_response")
    try:
        provider_date = date.fromisoformat(str(raw_date)[:10])
    except ValueError as exc:
        raise FxError("invalid_response") from exc
    parsed = {"USD": Decimal("1")}
    for code in ("CNY", "ILS"):
        if code not in rates:
            raise FxError("missing_currency")
        try:
            value = Decimal(str(rates[code]))
        except (InvalidOperation, ValueError) as exc:
            raise FxError("invalid_response") from exc
        if not value.is_finite() or value <= 0:
            raise FxError("invalid_rate")
        parsed[code] = value.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    return provider_date, parsed


def fetch_frankfurter(opener=None):
    import requests

    url = getattr(settings, "FX_PROVIDER_URL", "https://api.frankfurter.dev/v1/latest")
    timeout = float(getattr(settings, "FX_TIMEOUT_SECONDS", 10))
    params = {"base": "USD", "symbols": "CNY,ILS"}
    try:
        if opener is not None:
            response = opener(url, params, timeout)
        else:
            response = requests.get(url, params=params, timeout=(timeout, timeout))
    except requests.Timeout as exc:
        raise FxError("timeout") from exc
    except requests.RequestException as exc:
        raise FxError("network") from exc
    if getattr(response, "status_code", 200) >= 400:
        raise FxError("network")
    try:
        payload = response.json()
    except ValueError as exc:
        raise FxError("invalid_response") from exc
    return parse_frankfurter(payload)


def _same_rates(snapshot, provider_date, rates):
    if snapshot is None or snapshot.provider_date != provider_date or snapshot.provider != PROVIDER:
        return False
    current = snapshot_rates(snapshot)
    return current == rates


def publish_rates(provider_date, rates, fetched_at=None):
    """Replace the current snapshot only when CNY, USD and ILS are all valid."""
    if set(rates) != set(STORE_CURRENCIES) or any(value <= 0 for value in rates.values()):
        raise FxError("invalid_rate")
    fetched_at = fetched_at or timezone.now()
    FxRefreshLock.objects.get_or_create(pk=1)
    with transaction.atomic():
        FxRefreshLock.objects.select_for_update().get(pk=1)
        ensure_store_currencies()
        current = (
            RateSnapshot.objects.select_for_update()
            .filter(is_current=True)
            .order_by("-provider_date", "-fetched_at")
            .first()
        )
        if current is not None:
            current = RateSnapshot.objects.prefetch_related("lines").get(pk=current.pk)
        if _same_rates(current, provider_date, rates):
            current.fetched_at = fetched_at
            current.save(update_fields=["fetched_at"])
            log.info("exchange rates unchanged provider_date=%s", provider_date.isoformat())
            return current, False
        RateSnapshot.objects.filter(is_current=True).update(is_current=False)
        snapshot = RateSnapshot.objects.create(
            provider=PROVIDER,
            provider_date=provider_date,
            fetched_at=fetched_at,
            is_current=True,
        )
        RateSnapshotLine.objects.bulk_create([
            RateSnapshotLine(snapshot=snapshot, currency_id=code, usd_rate=rates[code])
            for code in STORE_CURRENCIES
        ])
        log.info("exchange rates published provider_date=%s", provider_date.isoformat())
        return snapshot, True


def refresh_exchange_rates(opener=None):
    try:
        provider_date, rates = fetch_frankfurter(opener)
        snapshot, created = publish_rates(provider_date, rates)
        return {"ok": True, "created": created, "snapshot": snapshot, "error": ""}
    except FxError as exc:
        log.warning("exchange rate refresh failed code=%s", exc.code)
        return {"ok": False, "created": False, "snapshot": current_snapshot(), "error": exc.code}


def snapshot_payload(snapshot=None):
    snapshot = current_snapshot() if snapshot is None else snapshot
    status = rate_status(snapshot)
    rates = snapshot_rates(snapshot) or {}
    return {
        "provider": snapshot.provider if snapshot else PROVIDER,
        "provider_date": None if snapshot is None else snapshot.provider_date.isoformat(),
        "fetched_at": None if snapshot is None else snapshot.fetched_at.isoformat(),
        "status": status,
        "checkout_allowed": checkout_allowed(status) if snapshot is not None else False,
        "rates": {code: f"{rates[code]:.8f}" for code in STORE_CURRENCIES if code in rates},
        "currencies": [
            {"code": code, "name": name, "symbol": symbol}
            for code, name, symbol in (
                ("CNY", "Chinese Yuan Renminbi", "¥"),
                ("USD", "US Dollar", "$"),
                ("ILS", "Israeli Shekel", "₪"),
            )
        ],
    }
