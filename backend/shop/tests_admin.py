import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from shop.models import Invoice, Order, OrderLine, PriceList, PriceListItem, Product, ProductImage


def product_body(**extra):
    body = {
        "name_ar": "منتج تجريبي",
        "name_en": "Sample product",
        "code": "RW-TEST-1",
        "category_id": 1,
        "base_price_ils": "10.00",
        "unit_ar": "قطعة",
        "unit_en": "piece",
        "min_qty": 2,
        "available": True,
        "options": ["افتراضي / Default"],
    }
    body.update(extra)
    return body


def import_row(**extra):
    row = {
        "Code": "RW-BULK-1",
        "Name_AR": "مستورد",
        "Name_EN": "Imported",
        "Category_ID": 1,
        "Unit_AR": "قطعة",
        "Unit_EN": "piece",
        "Min_Qty": 3,
        "Price_ILS": 12,
        "Available": 1,
        "Description_AR": "وصف",
        "Description_EN": "Description",
    }
    row.update(extra)
    return row


class AdminApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_dir = tempfile.TemporaryDirectory()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_dir.name)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        cls.media_dir.cleanup()

    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("staff", password="staff-pass", is_staff=True)

    def setUp(self):
        self.client = APIClient()

    def login_staff(self):
        return self.client.post(
            "/api/admin/auth/login/",
            {"username": "staff", "password": "staff-pass"},
            format="json",
        )

    def test_anonymous_admin_request_rejected(self):
        response = self.client.get("/api/admin/products/")
        self.assertEqual(response.status_code, 401)

    def test_trader_cannot_access_admin_api(self):
        self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        self.assertEqual(self.client.get("/api/admin/products/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/orders/").status_code, 403)

    def test_staff_admin_can_access_admin_api(self):
        self.login_staff()
        self.assertEqual(self.client.get("/api/admin/products/").status_code, 200)

    def test_valid_admin_login_and_me(self):
        response = self.login_staff()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["user"]["is_staff"])
        self.assertNotIn("password", response.data["user"])
        me = self.client.get("/api/admin/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["user"]["username"], "staff")

    def test_invalid_admin_login_rejected(self):
        response = self.client.post(
            "/api/admin/auth/login/",
            {"username": "staff", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        trader = self.client.post(
            "/api/admin/auth/login/",
            {"username": "trader", "password": "demo123"},
            format="json",
        )
        self.assertEqual(trader.status_code, 403)

    def test_seeded_admin_password_is_not_reset(self):
        user = User.objects.get(username="admin")
        user.set_password("changed-admin")
        user.save()
        call_command("seed_initial_data")
        user.refresh_from_db()
        self.assertTrue(user.check_password("changed-admin"))
        self.assertTrue(user.is_staff)

    def test_product_list_create_and_update(self):
        self.login_staff()
        created = self.client.post("/api/admin/products/", product_body(), format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["code"], "RW-TEST-1")
        self.assertEqual(created.data["base_price_ils"], "10.00")
        self.assertEqual(created.data["options"], ["افتراضي / Default"])
        updated = self.client.patch(
            f"/api/admin/products/{created.data['id']}/",
            {"name_en": "Updated sample", "available": False},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["name_en"], "Updated sample")
        self.assertFalse(updated.data["available"])
        self.assertEqual(len(self.client.get("/api/admin/products/").data), 9)

    def test_duplicate_code_rejected(self):
        self.login_staff()
        response = self.client.post("/api/admin/products/", product_body(code="RW-MN-001"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_minimum_and_negative_price_and_category(self):
        self.login_staff()
        self.assertEqual(self.client.post("/api/admin/products/", product_body(min_qty=0), format="json").status_code, 400)
        self.assertEqual(
            self.client.post("/api/admin/products/", product_body(base_price_ils="-1"), format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/admin/products/", product_body(category_id=999), format="json").status_code,
            400,
        )

    def test_product_image_upload_and_invalid_file(self):
        self.login_staff()
        product_id = self.client.post("/api/admin/products/", product_body(), format="json").data["id"]
        before = ProductImage.objects.filter(product_id=product_id).count()
        rejected = self.client.post(
            f"/api/admin/products/{product_id}/images/",
            {"file": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(ProductImage.objects.filter(product_id=product_id).count(), before)
        png = SimpleUploadedFile("cover.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png")
        uploaded = self.client.post(
            f"/api/admin/products/{product_id}/images/",
            {"file": png, "is_primary": "true"},
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 201)
        image = ProductImage.objects.get(pk=uploaded.data["id"])
        self.assertTrue(image.image)
        self.assertTrue(image.image.storage.exists(image.image.name))
        self.assertTrue(uploaded.data["url"].startswith("/media/"))
        self.assertTrue(image.is_primary)

    def test_category_create_and_image(self):
        self.login_staff()
        response = self.client.post(
            "/api/admin/categories/",
            {
                "name_ar": "أطفال",
                "name_en": "Kids",
                "image": SimpleUploadedFile("kids.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name_en"], "Kids")
        self.assertTrue(response.data["image"].startswith("/media/"))
        self.assertNotIn("All", response.data["name_en"])

    def test_trader_create_update_and_password(self):
        self.login_staff()
        created = self.client.post(
            "/api/admin/traders/",
            {
                "id": "north",
                "name_ar": "متجر الشمال",
                "name_en": "North Store",
                "username": "north",
                "email": "north@example.com",
                "price_list_id": "local",
                "active": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("password", created.data)
        self.assertNotIn("pbkdf2", str(created.data))
        user = User.objects.get(username="north")
        self.assertFalse(user.has_usable_password())
        updated = self.client.patch("/api/admin/traders/north/", {"name_en": "North Trading"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["name_en"], "North Trading")
        duplicate = self.client.post(
            "/api/admin/traders/",
            {
                "id": "other",
                "name_ar": "آخر",
                "name_en": "Other",
                "username": "trader",
                "price_list_id": "local",
                "active": True,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        changed = self.client.post("/api/admin/traders/north/set-password/", {"password": "secret-pass"}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertNotIn("pbkdf2", changed.content.decode())
        user.refresh_from_db()
        self.assertTrue(user.check_password("secret-pass"))
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertNotIn(user.password, changed.content.decode())

    def test_currency_and_price_list_rules(self):
        self.login_staff()
        currency = self.client.post(
            "/api/admin/currencies/",
            {"code": "eur", "name": "Euro", "symbol": "€"},
            format="json",
        )
        self.assertEqual(currency.status_code, 201)
        self.assertEqual(currency.data["code"], "EUR")
        lists = self.client.get("/api/admin/price-lists/")
        self.assertEqual(lists.status_code, 200)
        self.assertTrue(any(row["id"] == "local" and row["currency_code"] == "ILS" for row in lists.data))
        negative = self.client.put(
            "/api/admin/price-lists/local/prices/",
            {"prices": [{"product_id": 1, "price": "-1"}]},
            format="json",
        )
        self.assertEqual(negative.status_code, 400)
        before = PriceListItem.objects.filter(price_list_id="local").count()
        self.assertEqual(PriceListItem.objects.filter(price_list_id="local").count(), before)
        fallback = self.client.put(
            "/api/admin/price-lists/local/prices/",
            {"prices": [{"product_id": 1, "price": "10.00"}]},
            format="json",
        )
        self.assertEqual(fallback.status_code, 200)
        product = Product.objects.get(pk=8)
        self.assertEqual(PriceList.objects.get(pk="local").price_for(product), product.base_price_ils)
        created = self.client.post(
            "/api/admin/price-lists/",
            {"id": "gulf", "name_ar": "خليج", "name_en": "Gulf", "currency_code": "usd"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertFalse(created.data["complete"])
        partial = self.client.put(
            "/api/admin/price-lists/gulf/prices/",
            {"prices": [{"product_id": 1, "price": "5.00"}]},
            format="json",
        )
        self.assertEqual(partial.status_code, 400)
        self.assertEqual(PriceListItem.objects.filter(price_list_id="gulf").count(), 0)
        complete = self.client.put(
            "/api/admin/price-lists/gulf/prices/",
            {"prices": [{"product_id": product_id, "price": "5.00"} for product_id in Product.objects.values_list("id", flat=True)]},
            format="json",
        )
        self.assertEqual(complete.status_code, 200)
        self.assertTrue(complete.data["complete"])

    def test_admin_orders_and_status_do_not_change_prices(self):
        self.login_staff()
        listed = self.client.get("/api/admin/orders/")
        numbers = [row["number"] for row in listed.data]
        self.assertIn("RW-2026-1042", numbers)
        order = Order.objects.get(number="RW-2026-1042")
        total = order.total
        unit_prices = list(OrderLine.objects.filter(order=order).values_list("unit_price", flat=True))
        updated = self.client.patch(
            "/api/admin/orders/RW-2026-1042/status/",
            {"status": "confirmed", "total": "1.00", "trader_id": "atlas"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["status"], "confirmed")
        self.assertEqual(updated.data["total"], f"{total:.2f}")
        order.refresh_from_db()
        self.assertEqual(order.total, total)
        self.assertEqual(order.trader_id, "horizon")
        self.assertEqual(list(OrderLine.objects.filter(order=order).values_list("unit_price", flat=True)), unit_prices)
        rejected = self.client.patch("/api/admin/orders/RW-2026-1042/status/", {"status": "shipped"}, format="json")
        self.assertEqual(rejected.status_code, 400)

    def test_invoice_access_and_invalid_file(self):
        self.login_staff()
        rejected = self.client.post(
            "/api/admin/invoices/",
            {
                "number": "INV-BAD",
                "trader_id": "horizon",
                "date": "2026-10-06",
                "amount": "10.00",
                "file": SimpleUploadedFile("note.txt", b"not a pdf", content_type="text/plain"),
            },
            format="multipart",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(Invoice.objects.filter(number="INV-BAD").exists())
        created = self.client.post(
            "/api/admin/invoices/",
            {
                "number": "INV-TEST-1",
                "trader_id": "horizon",
                "date": "2026-10-06",
                "amount": "15.50",
                "file": SimpleUploadedFile("invoice.pdf", b"%PDF-1.4\n%", content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.data["file_url"].startswith("/media/"))
        self.client.post("/api/admin/auth/logout/")
        self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        own = self.client.get("/api/invoices/")
        self.assertEqual(own.status_code, 200)
        numbers = [row["number"] for row in own.data]
        self.assertIn("INV-TEST-1", numbers)
        self.assertIn("INV-2026-087", numbers)
        detail = self.client.get("/api/invoices/INV-TEST-1/")
        self.assertEqual(detail.status_code, 200)
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/login/", {"username": "export", "password": "demo123"}, format="json")
        self.assertEqual(self.client.get("/api/invoices/INV-TEST-1/").status_code, 404)
        self.assertNotIn("INV-TEST-1", [row["number"] for row in self.client.get("/api/invoices/").data])

    def test_settings_phone_rules(self):
        self.login_staff()
        invalid = self.client.patch("/api/admin/settings/", {"company_whatsapp_number": "123"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        valid = self.client.patch("/api/admin/settings/", {"company_whatsapp_number": "0599-123-4567"}, format="json")
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data["company_whatsapp_number"], "05991234567")
        self.client.post("/api/admin/auth/logout/")
        public = self.client.get("/api/settings/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data["company_whatsapp_number"], "05991234567")
        self.login_staff()
        empty = self.client.patch("/api/admin/settings/", {"company_whatsapp_number": ""}, format="json")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data["company_whatsapp_number"], "")

    def test_bulk_import_validation_and_rollback(self):
        self.login_staff()
        before = Product.objects.count()
        created = self.client.post("/api/admin/products/bulk-import/", {"rows": [import_row()]}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["created"], 1)
        self.assertEqual(created.data["products"][0]["image"], "men-shirt")
        self.assertEqual(created.data["products"][0]["options"], ["افتراضي / Default"])
        duplicate = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-MN-001")]},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        invalid_category = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-BULK-2", Category_ID=99)]},
            format="json",
        )
        self.assertEqual(invalid_category.status_code, 400)
        self.assertFalse(Product.objects.filter(code="RW-BULK-2").exists())
        rolled_back = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-BULK-3"), import_row(Code="RW-BULK-4", Category_ID=99)]},
            format="json",
        )
        self.assertEqual(rolled_back.status_code, 400)
        self.assertFalse(Product.objects.filter(code="RW-BULK-3").exists())
        untrusted = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-BULK-5", Available=True, Min_Qty="1.5", Base_Price_ILS="-3")]},
            format="json",
        )
        self.assertEqual(untrusted.status_code, 400)
        self.assertFalse(Product.objects.filter(code="RW-BULK-5").exists())
        self.assertEqual(Product.objects.count(), before + 1)
