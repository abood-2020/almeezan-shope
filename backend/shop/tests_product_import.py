from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from shop.models import Category, Product
from shop.tests_admin import import_row


ARABIC_HEADERS = {
    "كود المنتج": "RW-AR-IMPORT",
    "اسم المنتج (عربي)": "منتج القالب العربي",
    "اسم المنتج (إنجليزي)": "Arabic template product",
    "معرّف التصنيف": None,
    "وحدة البيع (عربي)": "علبة",
    "وحدة البيع (إنجليزي)": "box",
    "الحد الأدنى للكمية": 4,
    "السعر الأساسي (ILS)": "15.50",
    "متاح": 1,
    "الوصف (عربي)": "وصف عربي",
    "الوصف (إنجليزي)": "Arabic description",
    "السعر الأساسي (USD)": "99.00",
}


class ProductImportLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("import-staff", password="staff-pass", is_staff=True)
        cls.category_id = Category.objects.order_by("id").values_list("id", flat=True).first()

    def setUp(self):
        self.client = APIClient()
        self.client.post(
            "/api/admin/auth/login/",
            {"username": "import-staff", "password": "staff-pass"},
            format="json",
        )

    def arabic_row(self, **extra):
        row = dict(ARABIC_HEADERS)
        row["معرّف التصنيف"] = self.category_id
        row.update(extra)
        return row

    def test_arabic_headers_import_without_currency_conversion(self):
        existing = Product.objects.get(code="RW-MN-001")
        previous_price = existing.base_price_ils
        created = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.arabic_row()], "lang": "ar"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        product = Product.objects.get(code="RW-AR-IMPORT")
        self.assertEqual(product.name_ar, "منتج القالب العربي")
        self.assertEqual(product.name_en, "Arabic template product")
        self.assertEqual(product.category_id, self.category_id)
        self.assertEqual(product.unit_ar, "علبة")
        self.assertEqual(product.unit_en, "box")
        self.assertEqual(product.min_qty, 4)
        self.assertEqual(product.base_price_ils, Decimal("15.50"))
        self.assertIsNone(product.base_price_usd)
        self.assertTrue(product.available)
        self.assertEqual(product.description_ar, "وصف عربي")
        self.assertEqual(product.description_en, "Arabic description")
        existing.refresh_from_db()
        self.assertEqual(existing.base_price_ils, previous_price)
        self.assertEqual(existing.pk, Product.objects.get(code="RW-MN-001").pk)

    def test_english_headers_and_legacy_price_column(self):
        row = import_row(Code="RW-EN-IMPORT", Base_Price_ILS="18.25")
        row.pop("Price_ILS")
        english = self.client.post("/api/admin/products/bulk-import/", {"rows": [row], "lang": "en"}, format="json")
        self.assertEqual(english.status_code, 201, english.data)
        product = Product.objects.get(code="RW-EN-IMPORT")
        self.assertEqual(product.base_price_ils, Decimal("18.25"))
        self.assertIsNone(product.base_price_usd)
        legacy = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-LEGACY-IMPORT")], "lang": "en"},
            format="json",
        )
        self.assertEqual(legacy.status_code, 201, legacy.data)
        legacy_product = Product.objects.get(code="RW-LEGACY-IMPORT")
        self.assertEqual(legacy_product.base_price_ils, Decimal("12.00"))
        self.assertIsNone(legacy_product.base_price_usd)

    def test_whitespace_headers_map_and_duplicates_are_rejected(self):
        row = self.arabic_row()
        row["  كود المنتج  "] = row.pop("كود المنتج")
        spaced = self.client.post("/api/admin/products/bulk-import/", {"rows": [row], "lang": "ar"}, format="json")
        self.assertEqual(spaced.status_code, 201, spaced.data)
        conflict = self.arabic_row(**{"كود المنتج": "RW-DUP-HEADER", "Code": "RW-OTHER"})
        rejected = self.client.post("/api/admin/products/bulk-import/", {"rows": [conflict]}, format="json")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("أعمدة مكررة", rejected.data["rows"][0])
        self.assertFalse(Product.objects.filter(code="RW-DUP-HEADER").exists())
        self.assertFalse(Product.objects.filter(code="RW-OTHER").exists())
        both_prices = import_row(Code="RW-BOTH-PRICES", Base_Price_ILS="30")
        both = self.client.post("/api/admin/products/bulk-import/", {"rows": [both_prices], "lang": "en"}, format="json")
        self.assertEqual(both.status_code, 400)
        self.assertIn("duplicate columns", both.data["rows"][0])
        self.assertFalse(Product.objects.filter(code="RW-BOTH-PRICES").exists())

    def test_missing_unknown_and_invalid_values_do_not_write_rows(self):
        before = Product.objects.count()
        missing = dict(self.arabic_row())
        missing.pop("كود المنتج")
        missing["ProductCode"] = "RW-UNKNOWN"
        response = self.client.post("/api/admin/products/bulk-import/", {"rows": [missing]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("حقول مطلوبة", response.data["rows"][0])
        invalid_category = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [self.arabic_row(**{"كود المنتج": "RW-BAD-CAT", "معرّف التصنيف": 99})], "lang": "en"},
            format="json",
        )
        self.assertEqual(invalid_category.status_code, 400)
        self.assertIn("invalid category", invalid_category.data["rows"][0])
        invalid_number = self.client.post(
            "/api/admin/products/bulk-import/",
            {"rows": [import_row(Code="RW-BAD-NUM", Min_Qty="abc")], "lang": "en"},
            format="json",
        )
        self.assertEqual(invalid_number.status_code, 400)
        self.assertIn("invalid minimum", invalid_number.data["rows"][0])
        self.assertEqual(Product.objects.count(), before)

    def test_available_defaults_to_true_when_omitted_or_empty(self):
        row_empty_available = self.arabic_row(**{'كود المنتج': 'RW-DEF-AVAIL-1', 'متاح': ''})
        row_none_available = self.arabic_row(**{'كود المنتج': 'RW-DEF-AVAIL-2', 'متاح': None})
        row_omitted_available = self.arabic_row(**{'كود المنتج': 'RW-DEF-AVAIL-3'})
        del row_omitted_available['متاح']
        row_explicit_zero = self.arabic_row(**{'كود المنتج': 'RW-DEF-AVAIL-4', 'متاح': 0})
        row_arabic_yes = self.arabic_row(**{'كود المنتج': 'RW-DEF-AVAIL-5', 'متاح': 'نعم'})

        response = self.client.post(
            '/api/admin/products/bulk-import/',
            {'rows': [row_empty_available, row_none_available, row_omitted_available, row_explicit_zero, row_arabic_yes], 'lang': 'ar'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Product.objects.get(code='RW-DEF-AVAIL-1').available)
        self.assertTrue(Product.objects.get(code='RW-DEF-AVAIL-2').available)
        self.assertTrue(Product.objects.get(code='RW-DEF-AVAIL-3').available)
        self.assertFalse(Product.objects.get(code='RW-DEF-AVAIL-4').available)
        self.assertTrue(Product.objects.get(code='RW-DEF-AVAIL-5').available)
