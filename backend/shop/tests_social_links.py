from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from shop.content import ensure_social_links
from shop.models import SiteSetting, StoreSocialLink


class SocialLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        User.objects.create_user("social-trader", password="trader-pass")

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "admin", "password": "demo123"}, format="json")

    def links(self, admin=True):
        path = "/api/admin/settings/" if admin else "/api/settings/"
        if not admin:
            self.client.logout()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.data if hasattr(response, "data") else response.content)
        return response.data["social_links"]

    def save(self, rows, **extra):
        return self.client.patch("/api/admin/settings/", {"social_links": rows, **extra}, format="json")

    def test_two_facebooks_unknown_platform_edit_reorder_and_delete(self):
        created = self.save([
            {"name": "Facebook", "url": "https://facebook.com/page-one", "is_active": True},
            {"name": "Facebook", "url": "https://facebook.com/page-two", "is_active": True},
            {"name": "Instagram", "url": "https://instagram.com/store", "is_active": True},
            {"name": "TikTok", "url": "https://www.tiktok.com/@store", "is_active": True},
            {"name": "WeChat", "url": "https://weixin.qq.com/r/store", "is_active": True},
            {"name": "Future Platform", "url": "https://example.com/profile", "is_active": True},
        ])
        self.assertEqual(created.status_code, 200, created.data)
        names = [link["name"] for link in created.data["social_links"]]
        self.assertEqual(names.count("Facebook"), 2)
        self.assertIn("Future Platform", names)
        self.assertEqual(created.data["social_links"][0]["sort_order"], 0)
        edited = self.save([
            {"name": "Future Platform", "url": "https://example.com/profile", "is_active": True},
            {"name": "Facebook", "url": "https://facebook.com/page-one-edited", "is_active": True},
            {"name": "TikTok", "url": "http://tiktok.com/@store", "is_active": False},
        ])
        self.assertEqual(edited.status_code, 200, edited.data)
        saved = edited.data["social_links"]
        self.assertEqual([link["name"] for link in saved], ["Future Platform", "Facebook", "TikTok"])
        self.assertEqual(saved[1]["url"], "https://facebook.com/page-one-edited")
        self.assertFalse(saved[2]["is_active"])
        self.client.logout()
        public = self.client.get("/api/settings/")
        public_names = [link["name"] for link in public.data["social_links"]]
        self.assertEqual(public_names, ["Future Platform", "Facebook"])
        self.assertTrue(all(link["is_active"] for link in public.data["social_links"]))
        self.client.post("/api/admin/auth/login/", {"username": "admin", "password": "demo123"}, format="json")
        deleted = self.save([{"name": "Facebook", "url": "https://facebook.com/page-one-edited", "is_active": True}])
        self.assertEqual(deleted.status_code, 200, deleted.data)
        self.assertEqual(len(deleted.data["social_links"]), 1)

    def test_unsafe_names_and_urls_are_rejected(self):
        script = self.save([{"name": "Facebook", "url": "javascript:alert(1)"}])
        self.assertEqual(script.status_code, 400)
        data_url = self.save([{"name": "Facebook", "url": "data:text/html,hi"}])
        self.assertEqual(data_url.status_code, 400)
        markup = self.save([{"name": "<script>alert(1)</script>", "url": "https://example.com"}])
        self.assertEqual(markup.status_code, 400)
        self.assertFalse(StoreSocialLink.objects.filter(url__startswith="javascript:").exists())

    def test_legacy_facebook_and_instagram_copy_once(self):
        setting = SiteSetting.objects.get(pk=1)
        setting.facebook_url = "https://facebook.com/legacy"
        setting.instagram_url = "https://instagram.com/legacy"
        setting.social_links_migrated = False
        setting.save()
        StoreSocialLink.objects.filter(site=setting).delete()
        SiteSetting.objects.filter(pk=1).update(social_links_migrated=False)
        first = ensure_social_links(SiteSetting.objects.get(pk=1))
        second = ensure_social_links(SiteSetting.objects.get(pk=1))
        rows = list(first.social_links.order_by("sort_order").values_list("name", "url"))
        self.assertEqual(rows, [("Facebook", "https://facebook.com/legacy"), ("Instagram", "https://instagram.com/legacy")])
        self.assertEqual(second.social_links.count(), 2)
        self.assertTrue(SiteSetting.objects.get(pk=1).social_links_migrated)
        cleared = self.save([])
        self.assertEqual(cleared.status_code, 200, cleared.data)
        again = ensure_social_links(SiteSetting.objects.get(pk=1))
        self.assertEqual(again.social_links.count(), 0)
        self.assertEqual(again.facebook_url, "https://facebook.com/legacy")
        self.assertEqual(again.instagram_url, "https://instagram.com/legacy")

    def test_existing_matching_links_are_not_duplicated(self):
        setting = SiteSetting.objects.get(pk=1)
        setting.facebook_url = "https://facebook.com/kept"
        setting.instagram_url = ""
        setting.social_links_migrated = False
        setting.save()
        StoreSocialLink.objects.filter(site=setting).delete()
        StoreSocialLink.objects.create(site=setting, name="Facebook", url="https://facebook.com/kept", sort_order=0)
        SiteSetting.objects.filter(pk=1).update(social_links_migrated=False)
        ensure_social_links(SiteSetting.objects.get(pk=1))
        self.assertEqual(StoreSocialLink.objects.filter(name="Facebook", url="https://facebook.com/kept").count(), 1)

    def test_traders_and_guests_cannot_change_links(self):
        self.client.logout()
        guest = self.client.patch("/api/admin/settings/", {"social_links": []}, format="json")
        self.assertEqual(guest.status_code, 401)
        self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        trader = self.client.patch("/api/admin/settings/", {"social_links": []}, format="json")
        self.assertEqual(trader.status_code, 403)
