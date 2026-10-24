import threading
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from shop.models import Category, Invoice, Order, Trader, TraderCategoryDiscount
from shop.services import LAST_ADMIN_MESSAGE


ADMIN_PATHS = [
    "/api/admin/categories/",
    "/api/admin/products/",
    "/api/admin/traders/",
    "/api/admin/price-lists/",
    "/api/admin/currencies/",
    "/api/admin/orders/",
    "/api/admin/invoices/",
    "/api/admin/settings/",
    "/api/admin/fx/history/",
    "/api/admin/exchange-rates/",
]


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")

    def setUp(self):
        self.client = APIClient()

    def login(self, username, password="demo123"):
        return self.client.post(
            "/api/admin/auth/login/",
            {"username": username, "password": password},
            format="json",
        )

    def test_admin_promotes_a_trader_to_full_admin_without_superuser(self):
        self.login("admin")
        with self.assertLogs("shop.access", level="INFO") as captured:
            promoted = self.client.post("/api/admin/traders/horizon/promote/")
        self.assertEqual(promoted.status_code, 200, promoted.data)
        self.assertTrue(promoted.data["is_staff"])
        self.assertTrue(promoted.data["changed"])
        self.assertFalse(promoted.data["self"])
        self.assertTrue(promoted.data["trader"]["is_staff"])
        user = User.objects.get(username="trader")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("demo123"))
        self.assertNotIn("password", str(captured.output))
        self.assertNotIn("token", captured.output[0])
        self.assertIn("action=promote", captured.output[0])
        self.assertIn("previous_is_staff=False", captured.output[0])
        self.assertIn("new_is_staff=True", captured.output[0])
        again = self.client.post("/api/admin/traders/horizon/promote/")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertFalse(again.data["changed"])
        self.assertTrue(again.data["is_staff"])

    def test_promoted_admin_can_use_staff_apis_and_promote_another_trader(self):
        self.login("admin")
        self.assertEqual(self.client.post("/api/admin/traders/horizon/promote/").status_code, 200)
        promoted = APIClient()
        signed_in = promoted.post(
            "/api/admin/auth/login/",
            {"username": "trader", "password": "demo123"},
            format="json",
        )
        self.assertEqual(signed_in.status_code, 200, signed_in.data)
        self.assertTrue(signed_in.data["user"]["is_staff"])
        for path in ADMIN_PATHS:
            response = promoted.get(path)
            self.assertEqual(response.status_code, 200, path)
        for path in ("/api/admin/content/sections/", "/api/admin/faqs/"):
            response = promoted.get(path)
            self.assertNotIn(response.status_code, (401, 403), path)
        other = promoted.post("/api/admin/traders/atlas/promote/")
        self.assertEqual(other.status_code, 200, other.data)
        self.assertTrue(User.objects.get(username="export").is_staff)
        self.assertFalse(User.objects.get(username="export").is_superuser)

    def test_trader_and_anonymous_requests_cannot_change_admin_access(self):
        anonymous = self.client.post("/api/admin/traders/horizon/promote/")
        self.assertEqual(anonymous.status_code, 401)
        self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        self.assertEqual(self.client.post("/api/admin/traders/horizon/promote/").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/traders/atlas/promote/").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/traders/horizon/revoke/").status_code, 403)
        self.assertFalse(User.objects.get(username="trader").is_staff)
        self.assertFalse(User.objects.get(username="export").is_staff)

    def test_trader_profile_update_cannot_grant_admin_access(self):
        self.login("admin")
        updated = self.client.patch(
            "/api/admin/traders/horizon/",
            {"name_en": "Horizon Store", "is_staff": True, "is_superuser": True},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        user = User.objects.get(username="trader")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(updated.data["name_en"], "Horizon Store")

    def test_revoke_keeps_profile_pricing_orders_and_blocks_the_old_session(self):
        self.login("admin")
        self.client.post("/api/admin/traders/horizon/promote/")
        trader = Trader.objects.get(pk="horizon")
        TraderCategoryDiscount.objects.create(
            trader=trader,
            category=Category.objects.get(pk=1),
            discount_percent=Decimal("7.50"),
        )
        orders = Order.objects.filter(trader_id="horizon").count()
        invoices = Invoice.objects.filter(trader_id="horizon").count()
        self.assertGreater(orders, 0)
        session = APIClient()
        self.assertEqual(
            session.post("/api/admin/auth/login/", {"username": "trader", "password": "demo123"}, format="json").status_code,
            200,
        )
        self.assertEqual(session.get("/api/admin/products/").status_code, 200)
        with self.assertLogs("shop.access", level="INFO") as captured:
            revoked = self.client.post("/api/admin/traders/horizon/revoke/")
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.assertFalse(revoked.data["is_staff"])
        self.assertTrue(revoked.data["changed"])
        self.assertIn("action=revoke", captured.output[0])
        user = User.objects.get(username="trader")
        trader.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertEqual(trader.name_en, "Horizon Store")
        self.assertEqual(trader.price_list_id, "local")
        self.assertEqual(trader.category_discounts.get().discount_percent, Decimal("7.50"))
        self.assertEqual(Order.objects.filter(trader_id="horizon").count(), orders)
        self.assertEqual(Invoice.objects.filter(trader_id="horizon").count(), invoices)
        self.assertEqual(session.get("/api/admin/products/").status_code, 403)
        self.assertEqual(session.get("/api/admin/settings/").status_code, 403)
        me = session.get("/api/auth/me/")
        self.assertTrue(me.data["authenticated"])
        self.assertFalse(me.data["is_staff"])
        self.assertEqual(me.data["trader"]["id"], "horizon")
        repeated = self.client.post("/api/admin/traders/horizon/revoke/")
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertFalse(repeated.data["changed"])

    def test_last_active_administrator_cannot_be_revoked(self):
        self.login("admin")
        self.client.post("/api/admin/traders/horizon/promote/")
        User.objects.exclude(username="trader").update(is_staff=False)
        promoted = APIClient()
        promoted.post("/api/admin/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        revoked = promoted.post("/api/admin/traders/horizon/revoke/")
        self.assertEqual(revoked.status_code, 400, revoked.data)
        self.assertEqual(revoked.data["code"], "last_admin")
        self.assertEqual(revoked.data["detail"], LAST_ADMIN_MESSAGE)
        self.assertTrue(User.objects.get(username="trader").is_staff)
        self.assertEqual(promoted.get("/api/admin/traders/").status_code, 200)

    def test_self_revocation_is_allowed_when_another_active_administrator_remains(self):
        self.login("admin")
        self.client.post("/api/admin/traders/horizon/promote/")
        promoted = APIClient()
        promoted.post("/api/admin/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        revoked = promoted.post("/api/admin/traders/horizon/revoke/")
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.assertTrue(revoked.data["self"])
        self.assertFalse(revoked.data["is_staff"])
        self.assertEqual(promoted.get("/api/admin/orders/").status_code, 403)
        self.assertTrue(promoted.get("/api/auth/me/").data["authenticated"])
        self.assertTrue(User.objects.get(username="admin").is_staff)

    def test_inactive_trader_cannot_be_promoted(self):
        self.login("admin")
        Trader.objects.filter(pk="atlas").update(is_active=False)
        response = self.client.post("/api/admin/traders/atlas/promote/")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "inactive_account")
        self.assertFalse(User.objects.get(username="export").is_staff)


class LastAdminConcurrencyTests(TransactionTestCase):
    def setUp(self):
        call_command("seed_initial_data")
        User.objects.exclude(username__in=["trader", "export"]).update(is_staff=False)
        User.objects.filter(username__in=["trader", "export"]).update(is_staff=True, is_active=True)

    def test_concurrent_revocation_leaves_one_active_administrator(self):
        orders = Order.objects.filter(trader_id="horizon").count()
        connections.close_all()
        barrier = threading.Barrier(2)
        statuses = []
        errors = []

        def revoke(username, trader_id):
            try:
                close_old_connections()
                client = APIClient()
                signed_in = client.post(
                    "/api/admin/auth/login/",
                    {"username": username, "password": "demo123"},
                    format="json",
                )
                if signed_in.status_code != 200:
                    errors.append(f"{username} login {signed_in.status_code}")
                    return
                barrier.wait(timeout=10)
                response = client.post(f"/api/admin/traders/{trader_id}/revoke/")
                statuses.append(response.status_code)
            except Exception as exc:
                errors.append(repr(exc))
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=revoke, args=("trader", "horizon")),
            threading.Thread(target=revoke, args=("export", "atlas")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(statuses), [200, 400])
        self.assertEqual(User.objects.filter(is_staff=True, is_active=True).count(), 1)
        self.assertEqual(Trader.objects.filter(pk__in=["horizon", "atlas"]).count(), 2)
        self.assertEqual(Order.objects.filter(trader_id="horizon").count(), orders)
