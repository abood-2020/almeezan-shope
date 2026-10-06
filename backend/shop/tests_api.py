from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient
from django.test import TestCase

from shop.models import Order, OrderLine, PriceListItem, Product, ProductOption, Trader


class ShopApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")

    def setUp(self):
        self.client = APIClient()

    def login(self, username="trader", password="demo123"):
        return self.client.post(
            "/api/auth/login/",
            {"username": username, "password": password},
            format="json",
        )

    def test_csrf_endpoint(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["csrfToken"])
        self.assertIn("csrftoken", response.cookies)

    def test_login_with_csrf_header(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        response = client.post(
            "/api/auth/login/",
            {"username": "trader", "password": "demo123"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["trader"]["id"], "horizon")

    def test_valid_trader_login(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["trader"]["username"], "trader")
        self.assertNotIn("password", response.data["trader"])

    def test_wrong_password_rejected(self):
        response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 401)

    def test_inactive_trader_rejected(self):
        Trader.objects.filter(id="horizon").update(is_active=False)
        response = self.login()
        self.assertEqual(response.status_code, 403)

    def test_inactive_user_rejected(self):
        User.objects.filter(username="trader").update(is_active=False)
        response = self.login()
        self.assertEqual(response.status_code, 403)

    def test_user_without_trader_profile_rejected(self):
        User.objects.create_user(username="plain", password="demo123")
        response = self.login(username="plain")
        self.assertEqual(response.status_code, 403)

    def test_logout(self):
        self.login()
        response = self.client.post("/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me/").data["authenticated"])

    def test_me_guest(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["authenticated"])
        self.assertIsNone(response.data["trader"])

    def test_me_authenticated(self):
        self.login()
        trader = self.client.get("/api/auth/me/").data["trader"]
        self.assertEqual(trader["id"], "horizon")
        self.assertEqual(trader["name_ar"], "متجر الأفق")
        self.assertEqual(trader["name_en"], "Horizon Store")
        self.assertEqual(trader["email"], "trader@example.com")
        self.assertEqual(trader["price_list"]["id"], "local")
        self.assertEqual(trader["price_list"]["currency_code"], "ILS")
        self.assertEqual(trader["price_list"]["currency_symbol"], "₪")
        self.assertTrue(trader["active"])

    def test_guest_categories(self):
        response = self.client.get("/api/catalog/categories/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["name_en"] for row in response.data], ["Men", "Women", "Boys", "Girls"])
        self.assertEqual(response.data[0]["id"], 1)
        self.assertEqual(response.data[0]["image"], "men")

    def test_guest_catalog_hides_prices(self):
        response = self.client.get("/api/catalog/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 8)
        product = response.data[0]
        self.assertEqual(product["code"], "RW-MN-001")
        self.assertNotIn("price", product)
        self.assertNotIn("base_price_ils", product)
        self.assertNotIn("currency_code", product)
        self.assertIn("عاجي / Ivory · M", product["options"])
        detail = self.client.get("/api/catalog/products/1/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("price", detail.data)

    def test_authenticated_catalog_returns_ils_price(self):
        self.login()
        product = self.client.get("/api/catalog/products/1/").data
        self.assertEqual(product["price"], "82.00")
        self.assertEqual(product["currency_code"], "ILS")
        self.assertEqual(product["currency_symbol"], "₪")

    def test_export_trader_receives_usd_price(self):
        self.login(username="export")
        product = self.client.get("/api/catalog/products/1/").data
        self.assertEqual(product["price"], "25.00")
        self.assertEqual(product["currency_code"], "USD")
        self.assertEqual(product["currency_symbol"], "$")

    def test_current_price_list(self):
        self.login()
        response = self.client.get("/api/pricing/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], "local")
        self.assertEqual(response.data["currency_code"], "ILS")
        prices = {row["product_id"]: row["price"] for row in response.data["prices"]}
        self.assertEqual(prices[1], "82.00")
        self.assertEqual(prices[8], "73.00")

    def test_order_creation_ignores_client_money_and_trader(self):
        self.login()
        response = self.client.post(
            "/api/orders/",
            {
                "note": "Please confirm",
                "trader_id": "atlas",
                "status": "complete",
                "total": "1.00",
                "currency": "USD",
                "items": [
                    {"product_id": 1, "option": "عاجي / Ivory · M", "qty": 12, "price": "1.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        order = response.data
        self.assertTrue(order["number"].startswith("RW-2026-"))
        self.assertGreater(int(order["number"].rsplit("-", 1)[-1]), 1042)
        self.assertEqual(order["status"], "review")
        self.assertEqual(order["trader_name_ar"], "متجر الأفق")
        self.assertEqual(order["currency_code"], "ILS")
        self.assertEqual(order["currency_symbol"], "₪")
        self.assertEqual(order["total"], "984.00")
        self.assertEqual(order["items"][0]["unit_price"], "82.00")
        self.assertEqual(order["items"][0]["line_total"], "984.00")
        self.assertEqual(order["items"][0]["qty"], 12)
        self.assertEqual(order["note"], "Please confirm")
        stored = Order.objects.get(number=order["number"])
        self.assertEqual(stored.trader_id, "horizon")
        self.assertEqual(stored.total, Decimal("984.00"))
        self.assertEqual(stored.lines.get().unit_price, Decimal("82.00"))

    def test_minimum_quantity_enforced(self):
        self.login()
        response = self._order(1, "عاجي / Ivory · M", 10)
        self.assertEqual(response.status_code, 400)

    def test_unavailable_product_rejected(self):
        self.login()
        response = self._order(6, "رملي / Sand · M", 12)
        self.assertEqual(response.status_code, 400)

    def test_unavailable_option_rejected(self):
        self.login()
        ProductOption.objects.filter(product_id=1, label="عاجي / Ivory · M").update(is_available=False)
        response = self._order(1, "عاجي / Ivory · M", 12)
        self.assertEqual(response.status_code, 400)

    def test_missing_non_ils_price_rejected(self):
        self.login(username="export")
        PriceListItem.objects.filter(price_list_id="export", product_id=1).delete()
        response = self._order(1, "عاجي / Ivory · M", 12)
        self.assertEqual(response.status_code, 400)

    def test_empty_order_rejected(self):
        self.login()
        response = self.client.post("/api/orders/", {"note": "", "items": []}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unknown_product_rejected(self):
        self.login()
        response = self._order(999, "عاجي / Ivory · M", 12)
        self.assertEqual(response.status_code, 400)

    def test_trader_sees_only_own_orders(self):
        self.login()
        created = self._order(1, "عاجي / Ivory · M", 12).data["number"]
        own = self.client.get("/api/orders/")
        numbers = [row["number"] for row in own.data]
        self.assertIn("RW-2026-1042", numbers)
        self.assertIn(created, numbers)
        self.client.post("/api/auth/logout/")
        self.login(username="export")
        export_numbers = [row["number"] for row in self.client.get("/api/orders/").data]
        self.assertNotIn(created, export_numbers)
        self.assertNotIn("RW-2026-1042", export_numbers)
        self.assertEqual(self.client.get(f"/api/orders/{created}/").status_code, 404)
        detail = self.client.get("/api/orders/RW-2026-1042/")
        self.assertEqual(detail.status_code, 404)

    def test_owner_can_retrieve_order(self):
        self.login()
        number = self._order(2, "أبيض / White · M", 24).data["number"]
        response = self.client.get(f"/api/orders/{number}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"][0]["code"], "RW-MN-002")
        self.assertEqual(response.data["items"][0]["unit_price"], "45.00")

    def test_submitted_price_does_not_change_later(self):
        self.login()
        number = self._order(1, "عاجي / Ivory · M", 12).data["number"]
        PriceListItem.objects.filter(price_list_id="local", product_id=1).update(price=Decimal("1.00"))
        Product.objects.filter(id=1).update(base_price_ils=Decimal("1.00"))
        line = OrderLine.objects.get(order__number=number)
        self.assertEqual(line.unit_price, Decimal("82.00"))
        self.assertEqual(self.client.get(f"/api/orders/{number}/").data["items"][0]["unit_price"], "82.00")

    def _order(self, product_id, option, qty):
        return self.client.post(
            "/api/orders/",
            {"items": [{"product_id": product_id, "option": option, "qty": qty}]},
            format="json",
        )
