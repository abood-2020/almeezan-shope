from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from shop.fx import FxError, backfill_exchange_rates, parse_frankfurter, parse_frankfurter_series, publish_rates, refresh_exchange_rates
from shop.models import Category, Currency, PriceList, Product, RateObservation, RateSnapshot, Trader, TraderCategoryDiscount
from shop.pricing import quote_many


def _response(payload, status=200):
    class Response:
        status_code = status

        def json(self):
            return payload

    return Response()


class ExchangeRateTests(TestCase):
    def setUp(self):
        Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar", "symbol": "$"})
        Currency.objects.get_or_create(code="ILS", defaults={"name": "Israeli Shekel", "symbol": "₪"})
        Currency.objects.get_or_create(code="CNY", defaults={"name": "Chinese Yuan Renminbi", "symbol": "¥"})

    def test_parser_rejects_partial_and_bad_rates(self):
        date_value, rates = parse_frankfurter({"base": "USD", "date": "2026-10-10", "rates": {"CNY": "7.2", "ILS": "3.6"}})
        self.assertEqual(date_value, date(2026, 10, 10))
        self.assertEqual(rates["USD"], Decimal("1"))
        self.assertEqual(rates["CNY"], Decimal("7.20000000"))
        with self.assertRaises(FxError):
            parse_frankfurter({"base": "USD", "date": "2026-10-10", "rates": {"CNY": "7.2"}})
        with self.assertRaises(FxError):
            parse_frankfurter({"base": "EUR", "date": "2026-10-10", "rates": {"CNY": "1", "ILS": "1"}})
        with self.assertRaises(FxError):
            parse_frankfurter({"base": "USD", "date": "2026-10-10", "rates": {"CNY": "0", "ILS": "3"}})
        with self.assertRaises(FxError):
            parse_frankfurter({"base": "USD", "date": "2026-10-10", "rates": {"CNY": "-1", "ILS": "3"}})

    def test_refresh_replaces_atomically_and_keeps_the_last_good_snapshot(self):
        first, created = publish_rates(date(2026, 10, 9), {"USD": Decimal("1"), "CNY": Decimal("7.00000000"), "ILS": Decimal("3.00000000")})
        self.assertTrue(created)
        again, created_again = publish_rates(date(2026, 10, 9), {"USD": Decimal("1"), "CNY": Decimal("7.00000000"), "ILS": Decimal("3.00000000")})
        self.assertFalse(created_again)
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(RateSnapshot.objects.filter(is_current=True).count(), 1)

        def opener(url, params, timeout):
            return _response({"base": "USD", "date": "2026-10-10", "rates": {"CNY": "7.2", "ILS": "3.6"}})

        result = refresh_exchange_rates(opener)
        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshot"].provider, "frankfurter")
        self.assertEqual(result["snapshot"].provider_date, date(2026, 10, 10))
        self.assertFalse(RateSnapshot.objects.get(pk=first.pk).is_current)

        def fail(url, params, timeout):
            raise FxError("network")

        with patch("shop.fx.fetch_frankfurter", side_effect=FxError("timeout")):
            failed = refresh_exchange_rates()
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"], "timeout")
        self.assertEqual(failed["snapshot"].provider_date, date(2026, 10, 10))
        self.assertEqual(RateSnapshot.objects.filter(is_current=True).count(), 1)

    def test_management_command_uses_the_same_service(self):
        payload = {"base": "USD", "date": "2026-10-12", "rates": {"CNY": "7.1", "ILS": "3.7"}}
        with patch("shop.fx.fetch_frankfurter", return_value=parse_frankfurter(payload)):
            call_command("refresh_exchange_rates")
        self.assertEqual(RateSnapshot.objects.get(is_current=True).provider_date, date(2026, 10, 12))
        self.assertEqual(RateObservation.objects.get(provider_date=date(2026, 10, 12)).cny_per_usd, Decimal("7.10000000"))

    def test_backfill_keeps_snapshots_and_skips_duplicates(self):
        current, _created = publish_rates(date(2026, 10, 10), {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})
        payload = {"base": "USD", "rates": {
            "2026-01-02": {"CNY": "6.90000000", "ILS": "3.20000000"},
            "2026-01-03": {"CNY": "0", "ILS": "3.20000000"},
            "holiday": {"CNY": "6.1", "ILS": "3.1"},
            "2026-01-05": {"CNY": "7.10000000", "ILS": "3.30000000"},
        }}
        observations, failed = parse_frankfurter_series(payload)
        self.assertEqual(len(observations), 2)
        self.assertEqual(len(failed), 2)

        def opener(url, params, timeout):
            self.assertIn("2026-01-01..2026-01-31", url)
            return _response(payload)

        first = backfill_exchange_rates(date(2026, 1, 1), date(2026, 1, 31), opener)
        self.assertEqual(first["imported"], 2)
        self.assertEqual(first["failed"], 2)
        second = backfill_exchange_rates(date(2026, 1, 1), date(2026, 1, 31), opener)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["skipped"], 2)
        self.assertEqual(RateSnapshot.objects.get(is_current=True).pk, current.pk)
        self.assertEqual(RateObservation.objects.get(provider_date=date(2026, 10, 10)).cny_per_usd, Decimal("7.20000000"))
        self.assertEqual(RateObservation.objects.filter(provider_date=date(2026, 1, 2)).count(), 1)
        with self.assertRaises(CommandError):
            call_command("backfill_exchange_rates", start="2026-02-01", end="2026-01-01")

    def test_history_is_staff_only_and_paginates(self):
        User.objects.create_user("fx-history", password="staff-pass", is_staff=True)
        start_day = date(2026, 1, 2)
        for offset in range(31):
            day = date.fromordinal(start_day.toordinal() + offset)
            RateObservation.objects.create(
                provider="frankfurter",
                provider_date=day,
                fetched_at=timezone.now(),
                cny_per_usd=Decimal("6.50000000") + Decimal(offset) / Decimal("100000000"),
                ils_per_usd=Decimal("3.10000000"),
            )
        guest = APIClient()
        self.assertEqual(guest.get("/api/admin/fx/history/").status_code, 401)
        buyer = User.objects.create_user("fx-buyer", password="buyer-pass")
        trader_client = APIClient()
        trader_client.force_login(buyer)
        self.assertEqual(trader_client.get("/api/admin/fx/history/").status_code, 403)
        client = APIClient()
        client.post("/api/admin/auth/login/", {"username": "fx-history", "password": "staff-pass"}, format="json")
        page = client.get("/api/admin/fx/history/", {"from": "2026-01-01", "to": "2026-12-31", "page": 1})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["count"], 31)
        self.assertEqual(page.data["page_size"], 30)
        self.assertEqual(page.data["pages"], 2)
        self.assertEqual(len(page.data["results"]), 30)
        self.assertGreater(page.data["results"][0]["date"], page.data["results"][-1]["date"])
        second = client.get("/api/admin/fx/history/", {"from": "2026-01-01", "to": "2026-12-31", "page": 2})
        self.assertEqual(len(second.data["results"]), 1)
        exact = client.get("/api/admin/fx/history/", {"date": page.data["results"][0]["date"]})
        self.assertEqual(exact.data["count"], 1)
        self.assertEqual(exact.data["results"][0]["provider"], "Frankfurter")
        self.assertEqual(client.get("/api/admin/fx/history/", {"from": "2026-05-01", "to": "2026-01-01"}).status_code, 400)
        self.assertEqual(client.get("/api/admin/fx/history/", {"page": 9}).status_code, 400)


class OriginalPriceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("fx-staff", password="staff-pass", is_staff=True)
        cls.list = PriceList.objects.create(
            id="fx-list",
            name_ar="تحويل",
            name_en="Conversion",
            currency_id="USD",
            pricing_mode="rule_based",
            default_discount_percent=Decimal("0"),
        )
        publish_rates(date(2026, 10, 10), {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "fx-staff", "password": "staff-pass"}, format="json")

    def product(self, code, currency, amount):
        category = Category.objects.order_by("id").first()
        return Product.objects.create(
            category=category,
            name_ar=code,
            name_en=code,
            code=code,
            base_price_ils=amount if currency == "ILS" else Decimal("0"),
            original_price=amount,
            original_currency_id=currency,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
        )

    def quote(self, product, display):
        price_list = PriceList.objects.get(pk=self.list.pk)
        return quote_many(price_list, [product], display_currency=display)[product.id]

    def test_conversions_in_every_direction_and_original_stays_fixed(self):
        yuan = self.product("FX-CNY", "CNY", Decimal("100.00"))
        dollar = self.product("FX-USD", "USD", Decimal("20.00"))
        shekel = self.product("FX-ILS", "ILS", Decimal("75.00"))
        self.assertEqual(self.quote(yuan, "USD").unit_price, Decimal("13.89"))
        self.assertEqual(self.quote(yuan, "ILS").unit_price, Decimal("50.00"))
        self.assertEqual(self.quote(yuan, "CNY").unit_price, Decimal("100.00"))
        self.assertEqual(self.quote(dollar, "CNY").unit_price, Decimal("144.00"))
        self.assertEqual(self.quote(dollar, "ILS").unit_price, Decimal("72.00"))
        self.assertEqual(self.quote(shekel, "USD").unit_price, Decimal("20.83"))
        self.assertEqual(self.quote(shekel, "CNY").unit_price, Decimal("150.00"))
        publish_rates(date(2026, 10, 11), {"USD": Decimal("1"), "CNY": Decimal("8.00000000"), "ILS": Decimal("4.00000000")})
        yuan.refresh_from_db()
        self.assertEqual(yuan.original_price, Decimal("100.00"))
        self.assertEqual(yuan.original_currency_id, "CNY")
        self.assertEqual(self.quote(yuan, "USD").unit_price, Decimal("12.50"))

    def test_missing_rates_do_not_invent_a_price(self):
        RateSnapshot.objects.all().delete()
        product = self.product("FX-MISSING", "CNY", Decimal("100.00"))
        quote = self.quote(product, "USD")
        self.assertFalse(quote.available)
        self.assertEqual(quote.error, "missing_exchange_rate")
        self.assertIsNone(quote.unit_price)

    def test_ambiguous_legacy_prices_are_kept_for_review(self):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("shop.migrations.0007_original_prices_fx_and_trader_discounts")
        assign_original_prices = migration.assign_original_prices

        clear = Product.objects.get(code="RW-MN-001")
        clear.original_price = None
        clear.original_currency = None
        clear.base_price_usd = Decimal("40.00")
        clear.base_price_ils = Decimal("100.00")
        clear.price_review_required = False
        clear.save()
        only_ils = Product.objects.get(code="RW-MN-002")
        only_ils.original_price = None
        only_ils.original_currency = None
        only_ils.base_price_usd = None
        only_ils.base_price_ils = Decimal("45.00")
        only_ils.save()
        assign_original_prices(apps, None)
        clear.refresh_from_db()
        only_ils.refresh_from_db()
        self.assertTrue(clear.price_review_required)
        self.assertIsNone(clear.original_price)
        self.assertEqual(clear.base_price_usd, Decimal("40.00"))
        self.assertEqual(clear.base_price_ils, Decimal("100.00"))
        self.assertEqual(only_ils.original_currency_id, "ILS")
        self.assertEqual(only_ils.original_price, Decimal("45.00"))
        self.assertFalse(only_ils.price_review_required)


class TraderPricingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("discount-staff", password="staff-pass", is_staff=True)
        publish_rates(date(2026, 10, 10), {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "discount-staff", "password": "staff-pass"}, format="json")
        clothing = Category.objects.create(name_ar="ملابس الخصم", name_en="Discount clothing")
        men = Category.objects.create(name_ar="رجالي الخصم", name_en="Discount men", parent=clothing)
        shirts = Category.objects.create(name_ar="قمصان الخصم", name_en="Discount shirts", parent=men)
        shoes = Category.objects.create(name_ar="أحذية الخصم", name_en="Discount shoes")
        girls = Category.objects.create(name_ar="بنات الخصم", name_en="Discount girls")
        self.ids = {"men": men.id, "shirts": shirts.id, "shoes": shoes.id, "girls": girls.id}
        self.shirt = self._product("TD-SHIRT", shirts, Decimal("100.00"))
        self.shoe = self._product("TD-SHOE", shoes, Decimal("100.00"))
        self.girl = self._product("TD-GIRL", girls, Decimal("100.00"))
        self.other = self._product("TD-OTHER", clothing, Decimal("100.00"))

    def _product(self, code, category, amount):
        return Product.objects.create(
            category=category,
            name_ar=code,
            name_en=code,
            code=code,
            base_price_ils=Decimal("0"),
            original_price=amount,
            original_currency_id="CNY",
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
        )

    def test_admin_can_store_contact_details_and_isolated_category_discounts(self):
        trader = self.client.get("/api/admin/traders/horizon/")
        self.assertEqual(trader.status_code, 200)
        self.assertIn("phone", trader.data)
        saved = self.client.patch(
            "/api/admin/traders/horizon/",
            {
                "phone": "0599000000",
                "country": "فلسطين",
                "city": "الخليل",
                "category_discounts": [
                    {"category_id": self.ids["men"], "discount_percent": "7"},
                    {"category_id": self.ids["shirts"], "discount_percent": "10"},
                    {"category_id": self.ids["shoes"], "discount_percent": "2"},
                    {"category_id": self.ids["girls"], "discount_percent": "9"},
                ],
            },
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["phone"], "0599000000")
        self.assertEqual(saved.data["country"], "فلسطين")
        self.assertEqual(saved.data["city"], "الخليل")
        again = self.client.get("/api/admin/traders/horizon/")
        self.assertEqual(again.data["city"], "الخليل")
        self.assertEqual(len(again.data["category_discounts"]), 4)
        price_list = PriceList.objects.get(pk="local")
        price_list.pricing_mode = "rule_based"
        price_list.default_discount_percent = Decimal("0")
        price_list.save(update_fields=["pricing_mode", "default_discount_percent"])
        trader_row = Trader.objects.get(pk="horizon")
        quotes = quote_many(price_list, [self.shirt, self.shoe, self.girl, self.other], display_currency="USD", trader=trader_row)
        self.assertEqual(quotes[self.shirt.id].discount_percent, Decimal("10.00"))
        self.assertEqual(quotes[self.shirt.id].unit_price, Decimal("12.50"))
        self.assertEqual(quotes[self.shoe.id].discount_percent, Decimal("2.00"))
        self.assertEqual(quotes[self.girl.id].discount_percent, Decimal("9.00"))
        self.assertEqual(quotes[self.other.id].discount_percent, Decimal("0"))
        self.assertEqual(quotes[self.other.id].unit_price, Decimal("13.89"))
        other = quote_many(price_list, [self.shirt], display_currency="ILS", trader=Trader.objects.get(pk="atlas"))
        self.assertEqual(other[self.shirt.id].discount_percent, Decimal("0"))
        self.assertEqual(other[self.shirt.id].unit_price, Decimal("50.00"))
        self.assertEqual(PriceList.objects.get(pk="local").default_discount_percent, Decimal("0"))
        self.assertEqual(TraderCategoryDiscount.objects.filter(trader_id="atlas").count(), 0)

        trader_client = APIClient()
        trader_client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        denied = trader_client.patch("/api/admin/traders/atlas/", {"city": "غزة"}, format="json")
        self.assertEqual(denied.status_code, 403)
        refresh = trader_client.post("/api/admin/fx/refresh/", {}, format="json")
        self.assertEqual(refresh.status_code, 403)

    def test_stale_rates_stay_visible_and_old_rates_block_checkout(self):
        from datetime import timedelta

        from shop.fx import current_snapshot, rate_status

        recent = timezone.localdate() - timedelta(days=6)
        price_list = PriceList.objects.get(pk="local")
        price_list.pricing_mode = "rule_based"
        price_list.default_discount_percent = Decimal("0")
        price_list.save(update_fields=["pricing_mode", "default_discount_percent"])
        publish_rates(recent, {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})
        self.assertEqual(rate_status(current_snapshot()), "stale")
        shown = quote_many(PriceList.objects.get(pk="local"), [self.shirt], display_currency="USD")
        self.assertTrue(shown[self.shirt.id].available)
        self.assertTrue(shown[self.shirt.id].checkout_allowed)
        publish_rates(timezone.localdate() - timedelta(days=20), {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})
        blocked = quote_many(PriceList.objects.get(pk="local"), [self.shirt], display_currency="USD")
        self.assertTrue(blocked[self.shirt.id].available)
        self.assertFalse(blocked[self.shirt.id].checkout_allowed)

    def test_order_snapshot_keeps_the_discounted_price_after_rates_change(self):
        from shop.models import OrderLine, ProductOption

        price_list = PriceList.objects.get(pk="local")
        price_list.pricing_mode = "rule_based"
        price_list.default_discount_percent = Decimal("0")
        price_list.save(update_fields=["pricing_mode", "default_discount_percent"])
        TraderCategoryDiscount.objects.create(
            trader_id="horizon", category_id=self.ids["men"], discount_percent=Decimal("7.00")
        )
        ProductOption.objects.create(product=self.shirt, label="Default", is_available=True)
        trader_client = APIClient()
        self.assertEqual(
            trader_client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json").status_code,
            200,
        )
        rejected = trader_client.post(
            "/api/orders/",
            {"display_currency": "USD", "items": [{"product_id": self.shirt.id, "option": "Default", "qty": 1, "price": "1.00"}]},
            format="json",
        )
        self.assertEqual(rejected.status_code, 201)
        self.assertNotEqual(rejected.data["items"][0]["unit_price"], "1.00")
        created = trader_client.post(
            "/api/orders/",
            {
                "display_currency": "USD",
                "items": [{"product_id": self.shirt.id, "option": "Default", "qty": 1, "expected_unit_price": "12.92"}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["currency_code"], "USD")
        self.assertEqual(created.data["total"], "12.92")
        line = OrderLine.objects.get(order__number=created.data["number"])
        self.assertEqual(line.original_price, Decimal("100.00"))
        self.assertEqual(line.original_currency, "CNY")
        self.assertEqual(line.discount_percent, Decimal("7.00"))
        self.assertEqual(line.unit_price, Decimal("12.92"))
        self.assertEqual(line.order.rate_provider, "frankfurter")
        self.assertEqual(line.order.rate_provider_date, date(2026, 10, 10))
        publish_rates(date(2026, 10, 12), {"USD": Decimal("1"), "CNY": Decimal("8.00000000"), "ILS": Decimal("4.00000000")})
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("12.92"))
        self.assertEqual(line.original_price, Decimal("100.00"))
