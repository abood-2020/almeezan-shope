from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from shop.models import Category, ExchangeRate, OrderLine, PriceList, PriceListItem, Product, Trader
from shop.pricing import quote_many
from shop.services import default_price_list


class PricingRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("pricing-staff", password="staff-pass", is_staff=True)
        clothing = Category.objects.create(name_ar="ملابس", name_en="Clothing")
        men = Category.objects.create(name_ar="رجالي", name_en="Men", parent=clothing)
        shirts = Category.objects.create(name_ar="قمصان", name_en="Shirts", parent=men)
        accessories = Category.objects.create(name_ar="إكسسوارات", name_en="Accessories")
        cls.ids = {"clothing": clothing.id, "men": men.id, "shirts": shirts.id, "accessories": accessories.id}
        Product.objects.filter(id=1).update(category=shirts, base_price_ils=Decimal("100.00"), base_currency_id="ILS")
        Product.objects.filter(id=2).update(category=accessories, base_price_ils=Decimal("100.00"), base_currency_id="ILS")

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "pricing-staff", "password": "staff-pass"}, format="json")
        created = self.client.post(
            "/api/admin/price-lists/",
            {
                "id": "vip",
                "name_ar": "كبار التجار",
                "name_en": "VIP traders",
                "currency_code": "ILS",
                "pricing_mode": "rule_based",
                "default_discount_percent": "5.00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["discount_scope"], "all")
        self.list = PriceList.objects.get(pk="vip")

    def quote(self, product_id, price_list=None):
        price_list = PriceList.objects.prefetch_related("items", "scope_categories").get(pk=(price_list or self.list).pk)
        product = Product.objects.select_related("base_currency").get(pk=product_id)
        return quote_many(price_list, [product])[product_id]

    def test_independent_bases_never_convert(self):
        updated = self.client.patch("/api/admin/products/1/", {"base_price_usd": "40.00"}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["base_price_ils"], "100.00")
        self.assertEqual(updated.data["base_price_usd"], "40.00")
        self.assertEqual(self.client.patch("/api/admin/products/1/", {"base_price_usd": "-1"}, format="json").status_code, 400)
        usd_list = PriceList.objects.create(
            id="usd-vip",
            name_ar="دولار",
            name_en="Dollar list",
            currency_id="USD",
            pricing_mode="rule_based",
            default_discount_percent=Decimal("10.00"),
        )
        ils = self.quote(1)
        dollar = self.quote(1, usd_list)
        self.assertEqual(ils.unit_price, Decimal("95.00"))
        self.assertEqual(ils.base_currency, "ILS")
        self.assertIsNone(ils.exchange_rate)
        self.assertEqual(dollar.unit_price, Decimal("36.00"))
        self.assertEqual(dollar.base_price, Decimal("40.00"))
        self.assertEqual(dollar.base_currency, "USD")
        self.assertIsNone(dollar.exchange_rate)
        Product.objects.filter(id=1).update(base_price_ils=Decimal("80.00"))
        self.assertEqual(self.quote(1, usd_list).unit_price, Decimal("36.00"))
        self.assertEqual(self.quote(1).unit_price, Decimal("76.00"))
        ExchangeRate.objects.create(source_id="USD", target_id="ILS", rate=Decimal("3.70000000"))
        self.assertEqual(self.quote(1).unit_price, Decimal("76.00"))
        self.assertEqual(self.quote(1, usd_list).unit_price, Decimal("36.00"))
        self.assertIsNone(Product.objects.get(pk=2).base_price_usd)

    def test_missing_currency_base_is_unavailable(self):
        usd_list = PriceList.objects.create(
            id="usd-missing",
            name_ar="دولار",
            name_en="Dollar list",
            currency_id="USD",
            pricing_mode="rule_based",
            default_discount_percent=Decimal("10.00"),
        )
        missing = self.quote(2, usd_list)
        self.assertFalse(missing.available)
        self.assertIsNone(missing.unit_price)
        self.assertEqual(missing.error, "missing_price")
        self.assertIsNone(missing.base_price)
        self.assertEqual(self.quote(2).unit_price, Decimal("95.00"))
        self.assertIsNone(Product.objects.get(pk=2).base_price_usd)

    def test_global_and_fractional_discounts(self):
        self.assertEqual(self.quote(2).source, "discount")
        self.assertEqual(self.quote(2).unit_price, Decimal("95.00"))
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "7.25"}, format="json")
        self.list.refresh_from_db()
        self.assertEqual(self.quote(2).unit_price, Decimal("92.75"))
        self.assertEqual(self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "-1"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "100.01"}, format="json").status_code, 400)
        Product.objects.filter(id=2).update(base_price_ils=Decimal("10.00"))
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "33.33"}, format="json")
        self.list.refresh_from_db()
        self.assertEqual(self.quote(2).unit_price, Decimal("6.67"))
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "0"}, format="json")
        self.list.refresh_from_db()
        self.assertEqual(self.quote(1).unit_price, Decimal("100.00"))
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "100"}, format="json")
        self.list.refresh_from_db()
        self.assertEqual(self.quote(1).unit_price, Decimal("0.00"))

    def test_scope_includes_descendants_once_and_new_products_follow_it(self):
        self.client.patch(
            "/api/admin/price-lists/vip/",
            {"default_discount_percent": "10.00", "discount_scope": "categories", "scope_category_ids": [self.ids["clothing"], self.ids["men"]]},
            format="json",
        )
        self.list.refresh_from_db()
        shirt = self.quote(1)
        outside = self.quote(2)
        self.assertEqual(shirt.source, "discount")
        self.assertEqual(shirt.discount_percent, Decimal("10.00"))
        self.assertEqual(shirt.unit_price, Decimal("90.00"))
        self.assertEqual(outside.source, "base")
        self.assertEqual(outside.discount_percent, Decimal("0"))
        self.assertEqual(outside.unit_price, Decimal("100.00"))
        self.client.patch(
            "/api/admin/price-lists/vip/",
            {"discount_scope": "categories", "scope_category_ids": [self.ids["shirts"]]},
            format="json",
        )
        self.list.refresh_from_db()
        self.assertEqual(self.quote(1).unit_price, Decimal("90.00"))
        included = Product.objects.create(
            category_id=self.ids["shirts"],
            name_ar="قميص جديد",
            name_en="New shirt",
            code="RW-NEW-SHIRT",
            base_price_ils=Decimal("40.00"),
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
        )
        excluded = Product.objects.create(
            category_id=self.ids["accessories"],
            name_ar="خارج النطاق",
            name_en="Outside",
            code="RW-NEW-OUT",
            base_price_ils=Decimal("40.00"),
            base_price_usd=Decimal("12.00"),
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
        )
        self.assertEqual(self.quote(included.id).unit_price, Decimal("36.00"))
        self.assertEqual(self.quote(excluded.id).unit_price, Decimal("40.00"))
        self.client.patch("/api/admin/price-lists/vip/", {"discount_scope": "all"}, format="json")
        self.list.refresh_from_db()
        self.assertEqual(self.quote(excluded.id).unit_price, Decimal("36.00"))
        self.assertEqual(self.quote(excluded.id).source, "discount")

    def test_manual_price_stays_fixed_until_reset(self):
        saved = self.client.put(
            "/api/admin/price-lists/vip/prices/",
            {"prices": [{"product_id": 1, "price": "80.00"}]},
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "50"}, format="json")
        self.list.refresh_from_db()
        pinned = self.quote(1)
        automatic = self.quote(2)
        self.assertTrue(pinned.overridden)
        self.assertEqual(pinned.source, "override")
        self.assertIsNone(pinned.discount_percent)
        self.assertEqual(pinned.unit_price, Decimal("80.00"))
        self.assertEqual(pinned.calculated, Decimal("50.00"))
        self.assertEqual(automatic.unit_price, Decimal("50.00"))
        self.assertFalse(automatic.overridden)
        reset = self.client.put("/api/admin/price-lists/vip/prices/", {"prices": []}, format="json")
        self.assertEqual(reset.status_code, 200, reset.data)
        self.assertEqual(PriceListItem.objects.filter(price_list_id="vip").count(), 0)
        self.list.refresh_from_db()
        restored = self.quote(1)
        self.assertFalse(restored.overridden)
        self.assertEqual(restored.unit_price, Decimal("50.00"))
        duplicate = self.client.put(
            "/api/admin/price-lists/vip/prices/",
            {"prices": [{"product_id": 1, "price": "1"}, {"product_id": 1, "price": "2"}]},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_old_percentage_rules_and_exchange_rates_do_not_change_quotes(self):
        rule = self.client.post(
            "/api/admin/price-lists/vip/category-rules/",
            {"category_id": self.ids["shirts"], "discount_percent": "50.00"},
            format="json",
        )
        self.assertEqual(rule.status_code, 201, rule.data)
        product_rule = self.client.post(
            "/api/admin/price-lists/vip/product-rules/",
            {"product_id": 1, "discount_percent": "20.00"},
            format="json",
        )
        self.assertEqual(product_rule.status_code, 201, product_rule.data)
        rate = self.client.post("/api/admin/exchange-rates/", {"source": "USD", "target": "ILS", "rate": "3.70000000"}, format="json")
        self.assertEqual(rate.status_code, 201, rate.data)
        self.assertEqual(self.client.post("/api/admin/exchange-rates/", {"source": "USD", "target": "ILS", "rate": "0"}, format="json").status_code, 400)
        quoted = self.quote(1)
        self.assertEqual(quoted.unit_price, Decimal("95.00"))
        self.assertEqual(quoted.source, "discount")
        self.assertIsNone(quoted.exchange_rate)

    def test_legacy_prices_stay_until_conversion_and_then_as_overrides(self):
        local = PriceList.objects.get(pk="local")
        product = Product.objects.get(pk=1)
        self.assertEqual(local.pricing_mode, "legacy")
        self.assertEqual(local.price_for(product), Decimal("82.00"))
        preview = self.client.post("/api/admin/price-lists/local/pricing-mode/", {"pricing_mode": "rule_based", "confirm": False}, format="json")
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.data["confirm_required"])
        local.refresh_from_db()
        self.assertEqual(local.pricing_mode, "legacy")
        self.assertEqual(self.client.patch("/api/admin/price-lists/local/", {"pricing_mode": "rule_based"}, format="json").status_code, 400)
        confirmed = self.client.post("/api/admin/price-lists/local/pricing-mode/", {"pricing_mode": "rule_based", "confirm": True}, format="json")
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.data["pricing_mode"], "rule_based")
        local.refresh_from_db()
        self.assertEqual(local.items.count(), 8)
        self.assertEqual(local.price_for(product), Decimal("82.00"))
        self.assertEqual(self.quote(1, local).source, "override")

    def test_permissions_guest_prices_and_assignment(self):
        self.client.post("/api/admin/auth/logout/")
        self.assertEqual(self.client.get("/api/admin/exchange-rates/").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/price-lists/", {"id": "x", "name_ar": "س", "name_en": "X", "currency_code": "ILS"}, format="json").status_code, 401)
        guest = self.client.get("/api/catalog/products/1/")
        self.assertNotIn("price", guest.data)
        self.assertNotIn("base_price_ils", guest.data)
        self.assertNotIn("base_price_usd", guest.data)
        trader = APIClient()
        trader.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        self.assertEqual(trader.get("/api/admin/exchange-rates/").status_code, 403)
        self.assertEqual(trader.get("/api/admin/price-lists/").status_code, 403)
        self.assertEqual(trader.put("/api/admin/price-lists/vip/prices/", {"prices": []}, format="json").status_code, 403)
        own = trader.get("/api/pricing/current/")
        self.assertEqual(own.data["id"], "local")
        export = APIClient()
        export.post("/api/auth/login/", {"username": "export", "password": "demo123"}, format="json")
        self.assertEqual(export.get("/api/pricing/current/").data["id"], "export")
        self.assertNotEqual(export.get("/api/catalog/products/1/").data["price"], trader.get("/api/catalog/products/1/").data["price"])
        before = Trader.objects.get(pk="horizon").price_list_id
        self.client.post("/api/admin/auth/login/", {"username": "pricing-staff", "password": "staff-pass"}, format="json")
        marked = self.client.patch("/api/admin/price-lists/vip/", {"is_default": True, "default_discount_percent": "0"}, format="json")
        self.assertEqual(marked.status_code, 200, marked.data)
        self.assertEqual(Trader.objects.get(pk="horizon").price_list_id, before)
        self.assertEqual(default_price_list().id, "vip")
        staff_product = self.client.get("/api/admin/products/2/")
        self.assertEqual(staff_product.data["base_price_ils"], "100.00")
        self.assertIsNone(staff_product.data["base_price_usd"])

    def test_submitted_orders_keep_snapshots_and_price_changes_need_acknowledgement(self):
        historical = OrderLine.objects.order_by("id").first()
        self.assertIsNotNone(historical)
        historical_snapshot = (
            historical.unit_price,
            historical.quantity,
            historical.line_total,
            historical.discount_percent,
            historical.exchange_rate,
            historical.order.total,
        )
        trader = APIClient()
        trader.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        Trader.objects.filter(pk="horizon").update(price_list_id="vip")
        catalog = trader.get("/api/catalog/products/1/")
        detail = trader.get("/api/catalog/products/1/")
        current = trader.get("/api/pricing/current/")
        listed = next(row for row in current.data["prices"] if row["product_id"] == 1)
        self.assertEqual(catalog.data["price"], "95.00")
        self.assertEqual(detail.data["price"], "95.00")
        self.assertEqual(listed["price"], "95.00")
        self.assertIsNone(listed["exchange_rate"])
        created = trader.post(
            "/api/orders/",
            {"items": [{"product_id": 1, "option": "عاجي / Ivory · M", "qty": 12, "expected_unit_price": "80.00"}]},
            format="json",
        )
        self.assertEqual(created.status_code, 409, created.data)
        self.assertTrue(created.data["price_changed"])
        self.assertFalse(OrderLine.objects.filter(order__trader_id="horizon", product_id=1, unit_price=Decimal("80.00")).exists())
        accepted = trader.post(
            "/api/orders/",
            {
                "acknowledge_price_changes": True,
                "items": [{"product_id": 1, "option": "عاجي / Ivory · M", "qty": 12, "expected_unit_price": "80.00"}],
            },
            format="json",
        )
        self.assertEqual(accepted.status_code, 201, accepted.data)
        line = OrderLine.objects.get(order__number=accepted.data["number"])
        self.assertEqual(line.unit_price, Decimal("95.00"))
        self.assertEqual(line.base_price, Decimal("100.00"))
        self.assertEqual(line.base_currency, "ILS")
        self.assertEqual(line.discount_percent, Decimal("5.00"))
        self.assertIsNone(line.exchange_rate)
        self.assertEqual(line.line_total, Decimal("1140.00"))
        Product.objects.filter(id=1).update(base_price_ils=Decimal("1.00"))
        self.client.patch("/api/admin/price-lists/vip/", {"default_discount_percent": "50"}, format="json")
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("95.00"))
        self.assertEqual(line.line_total, Decimal("1140.00"))
        self.assertEqual(trader.get(f"/api/orders/{accepted.data['number']}/").data["items"][0]["unit_price"], "95.00")
        self.assertEqual(trader.get("/api/catalog/products/1/").data["price"], "0.50")
        changed = trader.post(
            "/api/orders/",
            {"items": [{"product_id": 1, "option": "عاجي / Ivory · M", "qty": 12, "expected_unit_price": "95.00"}]},
            format="json",
        )
        self.assertEqual(changed.status_code, 409, changed.data)
        historical.refresh_from_db()
        historical.order.refresh_from_db()
        self.assertEqual(
            (
                historical.unit_price,
                historical.quantity,
                historical.line_total,
                historical.discount_percent,
                historical.exchange_rate,
                historical.order.total,
            ),
            historical_snapshot,
        )
