import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from rest_framework.test import APIClient

from shop.excel_images import _excel_row
from shop.models import Category, Product
from shop.remote_images import tiny_png
from shop.services import import_products
from shop.tests_admin import import_row


def workbook(rows, image_cells=None):
    book = Workbook()
    sheet = book.active
    sheet.title = "Data"
    for row in rows:
        sheet.append(list(row))
    folder = Path(tempfile.mkdtemp())
    for index, cell in enumerate(image_cells or []):
        path = folder / f"picture-{index}.png"
        path.write_bytes(tiny_png())
        image = XLImage(str(path))
        image.anchor = cell
        sheet.add_image(image)
    payload = BytesIO()
    book.save(payload)
    return SimpleUploadedFile(
        "products.xlsx",
        payload.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class FakeResponse:
    def __init__(self, status=200, body=b"", location=""):
        self.status_code = status
        self._body = body
        self.headers = {"Location": location} if location else {}

    def iter_content(self, size):
        yield self._body

    def close(self):
        return None


def public_dns(*_args, **_kwargs):
    return [(2, 1, 6, "", ("8.8.8.8", 443))]


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductImageImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("image-staff", password="staff-pass", is_staff=True)
        cls.category_id = Category.objects.order_by("id").values_list("id", flat=True).first()

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "image-staff", "password": "staff-pass"}, format="json")

    def row(self, code, **extra):
        data = import_row(Code=code, Category_ID=self.category_id, Original_Currency="CNY", Original_Price="80")
        data.pop("Price_ILS", None)
        data.update(extra)
        return data

    def headers(self):
        sample = self.row("RW-IMG-SAMPLE")
        return list(sample.keys())

    def test_url_image_is_saved_on_the_matching_product(self):
        existing = Product.objects.get(code="RW-MN-001")
        previous_price = existing.base_price_ils
        previous_images = list(existing.images.values_list("id", "image_key", "image"))
        png = tiny_png()
        with patch("shop.remote_images.socket.getaddrinfo", public_dns), patch(
            "shop.remote_images.requests.get", return_value=FakeResponse(body=png)
        ):
            response = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-IMG-URL", Product_Image="https://cdn.example.com/product.png")], "lang": "en"},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(code="RW-IMG-URL")
        self.assertEqual(product.original_currency_id, "CNY")
        self.assertEqual(product.original_price, Decimal("80"))
        picture = product.images.get()
        self.assertTrue(picture.image.name.endswith(".png"))
        self.assertEqual(default_storage.open(picture.image.name).read(), png)
        self.assertNotEqual(picture.image_key, "men-shirt")
        existing.refresh_from_db()
        self.assertEqual(existing.base_price_ils, previous_price)
        self.assertEqual(list(existing.images.values_list("id", "image_key", "image")), previous_images)

    def test_missing_image_keeps_the_placeholder_and_old_workbook_imports(self):
        response = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-IMG-NONE", Category_ID=self.category_id)], "lang": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        picture = Product.objects.get(code="RW-IMG-NONE").images.get()
        self.assertEqual(picture.image_key, "men-shirt")
        self.assertFalse(picture.image)

    def test_invalid_private_and_oversized_urls_do_not_create_products(self):
        before = Product.objects.count()
        invalid = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-IMG-BAD", Product_Image="javascript:alert(1)")], "lang": "en"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("unsafe image URL", invalid.data["rows"][0])
        private = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-IMG-LOCAL", Product_Image="http://127.0.0.1/secret.png")], "lang": "en"},
            format="json",
        )
        self.assertEqual(private.status_code, 400)
        self.assertIn("unsafe image URL", private.data["rows"][0])
        with patch("shop.remote_images.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.1.1.1", 80))]):
            resolved = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-IMG-DNS", Product_Image="http://intranet.example/a.png")], "lang": "en"},
                format="json",
            )
        self.assertEqual(resolved.status_code, 400)
        with patch("shop.remote_images.socket.getaddrinfo", public_dns), patch(
            "shop.remote_images.requests.get", side_effect=requests.Timeout("slow")
        ):
            timed = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-IMG-SLOW", Product_Image="https://cdn.example.com/slow.png")], "lang": "en"},
                format="json",
            )
        self.assertEqual(timed.status_code, 400)
        self.assertIn("timed out", timed.data["rows"][0])
        with patch("shop.remote_images.MAX_IMAGE_BYTES", 32), patch("shop.remote_images.socket.getaddrinfo", public_dns), patch(
            "shop.remote_images.requests.get", return_value=FakeResponse(body=b"x" * 64)
        ):
            large = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-IMG-BIG", Product_Image="https://cdn.example.com/big.png")], "lang": "en"},
                format="json",
            )
        self.assertEqual(large.status_code, 400)
        self.assertIn("too large", large.data["rows"][0])
        self.assertEqual(Product.objects.count(), before)

    def test_redirect_to_private_network_is_rejected(self):
        def redirected(url, **_kwargs):
            self.assertNotIn("127.0.0.1", url)
            return FakeResponse(status=302, location="http://127.0.0.1/secret.png")

        with patch("shop.remote_images.socket.getaddrinfo", public_dns), patch("shop.remote_images.requests.get", redirected):
            response = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-IMG-REDIRECT", Product_Image="https://cdn.example.com/go.png")], "lang": "en"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(code="RW-IMG-REDIRECT").exists())

    def test_embedded_image_follows_its_row_and_conflicts_are_explicit(self):
        headers = self.headers()
        first = [self.row("RW-IMG-ROW1")[key] for key in headers]
        second = [self.row("RW-IMG-ROW2")[key] for key in headers]
        uploaded = workbook([headers, first, second], ["M3"])
        response = self.client.post("/api/admin/products/bulk-import/", {"file": uploaded, "lang": "en"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Product.objects.get(code="RW-IMG-ROW1").images.get().image_key, "men-shirt")
        self.assertTrue(Product.objects.get(code="RW-IMG-ROW2").images.get().image)
        before = Product.objects.count()
        conflict_row = self.row("RW-IMG-BOTH", Product_Image="https://cdn.example.com/a.png")
        conflict_headers = list(conflict_row.keys())
        conflict = workbook([conflict_headers, [conflict_row[key] for key in conflict_headers]], ["M2"])
        rejected = self.client.post("/api/admin/products/bulk-import/", {"file": conflict, "lang": "en"}, format="multipart")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("both an image URL and an embedded image", rejected.data["rows"][0])
        multiple = workbook([headers, [self.row("RW-IMG-MULTI")[key] for key in headers]], ["M2", "L2"])
        many = self.client.post("/api/admin/products/bulk-import/", {"file": multiple, "lang": "en"}, format="multipart")
        self.assertEqual(many.status_code, 400)
        self.assertIn("multiple images", many.data["rows"][0])
        corrupt = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-IMG-CORRUPT")], "lang": "en"},
            format="json",
        )
        self.assertEqual(corrupt.status_code, 201, corrupt.data)
        try:
            import_products([self.row("RW-IMG-BYTES")], lang="en", embedded={0: [b"this is not an image!!"]})
        except Exception as exc:
            self.assertIn("unsupported", str(exc))
        else:
            self.fail("corrupted image was accepted")
        self.assertFalse(Product.objects.filter(code="RW-IMG-BYTES").exists())
        self.assertEqual(Product.objects.count(), before + 1)

    def test_failed_import_removes_saved_image_files(self):
        real_create = Product.objects.create
        calls = {"count": 0}

        def fail_second(**kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("stop")
            return real_create(**kwargs)

        png = tiny_png()
        with patch("shop.remote_images.socket.getaddrinfo", public_dns), patch(
            "shop.remote_images.requests.get", return_value=FakeResponse(body=png)
        ), patch("shop.services.Product.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                import_products([
                    self.row("RW-IMG-ROLLBACK-1", Product_Image="https://cdn.example.com/one.png"),
                    self.row("RW-IMG-ROLLBACK-2", Product_Image="https://cdn.example.com/two.png"),
                ])
        self.assertFalse(Product.objects.filter(code__startswith="RW-IMG-ROLLBACK").exists())
        self.assertFalse(default_storage.exists("products/RW-IMG-ROLLBACK-1.png"))

    def test_duplicate_code_does_not_replace_an_existing_image(self):
        existing = Product.objects.get(code="RW-MN-001")
        before = list(existing.images.values_list("id", "image", "image_key"))
        response = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-MN-001", Product_Image="https://cdn.example.com/new.png")], "lang": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        existing.refresh_from_db()
        self.assertEqual(list(existing.images.values_list("id", "image", "image_key")), before)

    def test_preview_reads_images_without_creating_products(self):
        before = Product.objects.count()
        headers = self.headers()
        uploaded = workbook([headers, [self.row("RW-IMG-PREVIEW")[key] for key in headers]], ["M2"])
        response = self.client.post("/api/admin/products/import-preview/", {"file": uploaded}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["images"][0]["status"], "ok")
        self.assertEqual(response.data["images"][0]["row"], 2)
        self.assertTrue(response.data["images"][0]["preview"].startswith("data:image/png"))
        self.assertEqual(Product.objects.count(), before)
        self.assertIsNone(_excel_row(type("Anchor", (), {"_from": None})()))

    def test_guests_cannot_import(self):
        self.client.logout()
        response = self.client.post("/api/admin/products/bulk-import/", {"rows": [self.row("RW-IMG-GUEST")]}, format="json")
        self.assertIn(response.status_code, {401, 403})
        self.assertFalse(Product.objects.filter(code="RW-IMG-GUEST").exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CategoryMappingImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        User.objects.create_user("map-staff", password="staff-pass", is_staff=True)
        cls.category_id = Category.objects.order_by("id").values_list("id", flat=True).first()
        cls.other_id = Category.objects.exclude(pk=cls.category_id).order_by("id").values_list("id", flat=True).first()

    def setUp(self):
        self.client = APIClient()
        self.client.post("/api/admin/auth/login/", {"username": "map-staff", "password": "staff-pass"}, format="json")

    def row(self, code, category):
        return import_row(Code=code, Category_ID=category)

    def test_unknown_category_can_be_mapped_and_is_rechecked(self):
        before = Product.objects.count()
        unknown = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-CAT-99", 99), self.row("RW-CAT-99B", 99)], "lang": "en"},
            format="json",
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("invalid category: 99", unknown.data["rows"][0])
        self.assertIn("invalid category: 99", unknown.data["rows"][1])
        self.assertEqual(Product.objects.count(), before)
        missing = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-CAT-BLANK", "")], "lang": "ar"},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("معرّف التصنيف غير موجود", missing.data["rows"][0])
        mapped = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-CAT-MAP", 99), self.row("RW-CAT-MAP-2", 99)], "lang": "en", "category_map": {"99": self.category_id}},
            format="json",
        )
        self.assertEqual(mapped.status_code, 201, mapped.data)
        self.assertEqual(Product.objects.get(code="RW-CAT-MAP").category_id, self.category_id)
        self.assertEqual(Product.objects.get(code="RW-CAT-MAP-2").category_id, self.category_id)
        bad_map = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.row("RW-CAT-BADMAP", 99)], "lang": "en", "category_map": {"99": 987654}},
            format="json",
        )
        self.assertEqual(bad_map.status_code, 400)
        self.assertFalse(Product.objects.filter(code="RW-CAT-BADMAP").exists())
        if self.other_id:
            kept = self.client.post(
                "/api/admin/products/bulk-import/",
                {"rows": [self.row("RW-CAT-KEEP", self.category_id)], "lang": "en", "category_map": {str(self.category_id): self.other_id}},
                format="json",
            )
            self.assertEqual(kept.status_code, 201, kept.data)
            self.assertEqual(Product.objects.get(code="RW-CAT-KEEP").category_id, self.category_id)
