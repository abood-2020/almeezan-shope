from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from shop.models import Currency, GoogleAccount, PriceList, Trader


CLIENT_ID = "test-client.apps.googleusercontent.com"


def claims(**extra):
    row = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-subject-1",
        "email": "new.trader@example.com",
        "email_verified": True,
        "name": "New Trader",
    }
    row.update(extra)
    return row


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleTraderAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        Currency.objects.get_or_create(code="ILS", defaults={"name": "Shekel", "symbol": "₪"})
        PriceList.objects.create(
            id="standard",
            name_ar="القائمة الأساسية",
            name_en="Standard",
            currency_id="ILS",
            pricing_mode=PriceList.PricingMode.RULE_BASED,
            default_discount_percent=Decimal("0"),
            is_default=True,
            is_active=True,
        )
        PriceList.objects.create(
            id="special",
            name_ar="خاصة",
            name_en="Special",
            currency_id="ILS",
            pricing_mode=PriceList.PricingMode.RULE_BASED,
            default_discount_percent=Decimal("10"),
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()

    def google(self, token="signed-token", error=None, identity=None, **body):
        payload = {"credential": token, **body}
        patcher = patch("shop.google_auth.id_token.verify_oauth2_token", return_value=identity or claims())
        if error is not None:
            patcher = patch("shop.google_auth.id_token.verify_oauth2_token", side_effect=error)
        with patcher:
            return self.client.post("/api/auth/google/", payload, format="json")

    def test_first_google_login_creates_a_trader_on_the_zero_percent_list(self):
        before = User.objects.count()
        response = self.google()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["profile_required"])
        trader = Trader.objects.get(user__email="new.trader@example.com")
        self.assertEqual(trader.price_list_id, "standard")
        self.assertEqual(trader.price_list.default_discount_percent, Decimal("0"))
        self.assertFalse(trader.user.is_staff)
        self.assertFalse(trader.user.is_superuser)
        self.assertFalse(trader.user.has_usable_password())
        self.assertEqual(GoogleAccount.objects.get(user=trader.user).sub, "google-subject-1")
        self.assertEqual(User.objects.count(), before + 1)
        self.assertEqual(self.client.get("/api/admin/auth/me/").status_code, 403)

    def test_returning_google_login_reuses_the_account_and_keeps_its_price_list(self):
        self.google()
        trader = Trader.objects.get(user__email="new.trader@example.com")
        trader.price_list_id = "special"
        trader.save(update_fields=["price_list"])
        again = self.google()
        self.assertEqual(again.status_code, 200, again.data)
        trader.refresh_from_db()
        self.assertEqual(trader.price_list_id, "special")
        self.assertEqual(GoogleAccount.objects.count(), 1)
        self.assertEqual(User.objects.filter(email="new.trader@example.com").count(), 1)

    def test_invalid_expired_and_wrong_audience_tokens_are_rejected(self):
        malformed = self.client.post("/api/auth/google/", {"credential": "not a token"}, format="json")
        self.assertEqual(malformed.status_code, 401)
        self.assertEqual(malformed.data["code"], "malformed")
        expired = self.google(error=ValueError("Token expired"))
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.data["code"], "expired")
        with patch("shop.google_auth.id_token.verify_oauth2_token", return_value=claims(aud="other-client")):
            audience = self.client.post("/api/auth/google/", {"credential": "signed-token"}, format="json")
        self.assertEqual(audience.status_code, 401)
        self.assertEqual(audience.data["code"], "audience")
        with patch("shop.google_auth.id_token.verify_oauth2_token", return_value=claims(iss="https://evil.example")):
            issuer = self.client.post("/api/auth/google/", {"credential": "signed-token"}, format="json")
        self.assertEqual(issuer.status_code, 401)
        self.assertEqual(issuer.data["code"], "issuer")
        self.assertFalse(GoogleAccount.objects.exists())

    def test_unverified_email_and_existing_email_do_not_create_or_link_accounts(self):
        existing = User.objects.get(username="trader")
        existing.email = "new.trader@example.com"
        existing.save(update_fields=["email"])
        assigned = Trader.objects.get(user=existing).price_list_id
        with patch("shop.google_auth.id_token.verify_oauth2_token", return_value=claims(email_verified=False)):
            unverified = self.client.post("/api/auth/google/", {"credential": "signed-token"}, format="json")
        self.assertEqual(unverified.status_code, 401)
        self.assertEqual(unverified.data["code"], "unverified_email")
        conflict = self.google()
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "email_exists")
        self.assertFalse(GoogleAccount.objects.exists())
        self.assertFalse(existing.trader.user.is_staff)
        self.assertEqual(Trader.objects.get(user=existing).price_list_id, assigned)
        self.assertFalse(self.client.get("/api/auth/me/").data["authenticated"])

    def test_request_email_is_ignored_and_profile_can_be_completed(self):
        response = self.google(email="intruder@example.com")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["trader"]["email"], "new.trader@example.com")
        profile = self.client.post(
            "/api/auth/google/profile/",
            {"business_name": "متجر النور", "phone": "0599-123-456", "country": "فلسطين", "city": "رام الله"},
            format="json",
        )
        self.assertEqual(profile.status_code, 200, profile.data)
        self.assertFalse(profile.data["profile_required"])
        trader = Trader.objects.get(pk=profile.data["trader"]["id"])
        self.assertEqual(trader.name_ar, "متجر النور")
        self.assertEqual(trader.phone, "0599123456")
        self.assertEqual(trader.country, "فلسطين")
        self.assertEqual(trader.city, "رام الله")
        self.assertEqual(trader.price_list.default_discount_percent, Decimal("0"))
        self.client.logout()
        again = self.google()
        self.assertFalse(again.data["profile_required"])

    def test_password_login_and_logout_still_work(self):
        logged_in = self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        self.assertEqual(logged_in.status_code, 200, logged_in.data)
        self.assertFalse(logged_in.data["trader"]["username"] == "")
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me/").data["authenticated"])
        staff = self.client.post("/api/admin/auth/login/", {"username": "admin", "password": "demo123"}, format="json")
        self.assertEqual(staff.status_code, 200, staff.data)
        self.assertTrue(staff.data["user"]["is_staff"])
        self.assertEqual(self.client.post("/api/admin/auth/logout/").status_code, 200)
        self.assertEqual(
            self.client.post("/api/auth/login/", {"username": "trader", "password": "wrong"}, format="json").status_code,
            401,
        )

    def test_missing_default_price_list_does_not_create_a_trader(self):
        PriceList.objects.filter(pk="standard").update(is_default=False)
        before = Trader.objects.count()
        response = self.google()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "no_default_price_list")
        self.assertEqual(Trader.objects.count(), before)
