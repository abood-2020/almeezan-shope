from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from shop.models import Category, Product, category_descendant_ids


class CategoryHierarchyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")
        cls.staff = User.objects.create_user("hierarchy-staff", password="staff-pass", is_staff=True)

    def setUp(self):
        self.client = APIClient()

    def login_staff(self):
        self.client.post(
            "/api/admin/auth/login/",
            {"username": "hierarchy-staff", "password": "staff-pass"},
            format="json",
        )

    def test_existing_categories_and_products_stay_in_place(self):
        self.assertEqual(
            list(Category.objects.order_by("id").values_list("id", "name_en", "parent_id")),
            [(1, "Men", None), (2, "Women", None), (3, "Boys", None), (4, "Girls", None)],
        )
        self.assertEqual(Product.objects.get(id=1).category_id, 1)
        self.assertEqual(Product.objects.get(id=7).category_id, 4)

    def test_three_levels_and_rejection_of_a_fourth(self):
        root = Category.objects.create(name_ar="ملابس", name_en="Clothing")
        second = Category.objects.create(name_ar="رجالي فرعي", name_en="Menswear", parent=root)
        third = Category.objects.create(name_ar="قمصان", name_en="Shirts", parent=second)
        self.assertIsNone(root.parent_id)
        self.assertEqual(second.parent_id, root.id)
        self.assertEqual(third.parent_id, second.id)
        fourth = Category(name_ar="كتان", name_en="Linen", parent=third)
        with self.assertRaises(ValidationError):
            fourth.full_clean()
        self.assertFalse(Category.objects.filter(name_en="Linen").exists())
        self.assertEqual(Product.objects.get(id=1).category_id, 1)

    def test_self_parent_and_cycles_are_rejected(self):
        root = Category.objects.get(pk=1)
        root.parent = root
        with self.assertRaises(ValidationError):
            root.full_clean()
        child = Category.objects.create(name_ar="فرعي", name_en="Branch", parent_id=1)
        root.parent = child
        with self.assertRaises(ValidationError):
            root.full_clean()
        root.refresh_from_db()
        self.assertIsNone(root.parent_id)

    def test_move_is_rejected_when_descendants_would_pass_level_three(self):
        root = Category.objects.create(name_ar="جذر", name_en="Root")
        child = Category.objects.create(name_ar="ابن", name_en="Child", parent=root)
        Category.objects.create(name_ar="حفيد", name_en="Grandchild", parent=child)
        other = Category.objects.create(name_ar="آخر", name_en="Other")
        root.parent = other
        with self.assertRaises(ValidationError):
            root.full_clean()
        child.parent = other
        child.full_clean()
        child.save()
        child.refresh_from_db()
        self.assertEqual(child.parent_id, other.id)

    def test_descendant_filter_includes_nested_products(self):
        child = Category.objects.create(name_ar="قمصان رجالية", name_en="Men shirts", parent_id=1)
        product = Product.objects.get(code="RW-MN-001")
        original_category = product.category_id
        product.category = child
        product.save()
        self.assertIn(product.id, Product.objects.filter(category_id__in=category_descendant_ids(1)).values_list("id", flat=True))
        self.assertEqual(list(category_descendant_ids(child.id)), [child.id])
        response = self.client.get("/api/catalog/products/", {"category": 1})
        self.assertEqual(response.status_code, 200)
        self.assertIn("RW-MN-001", [row["code"] for row in response.data])
        self.assertTrue(all(row["category_id"] in category_descendant_ids(1) for row in response.data))
        product.category_id = original_category
        product.save()

    def test_category_api_keeps_ids_and_reports_hierarchy(self):
        child = Category.objects.create(name_ar="قمصان", name_en="Shirts", parent_id=1, sort_order=1)
        response = self.client.get("/api/catalog/categories/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data}
        self.assertEqual(rows[1]["name_en"], "Men")
        self.assertIsNone(rows[1]["parent_id"])
        self.assertEqual(rows[1]["level"], 1)
        self.assertIn(child.id, rows[1]["children"])
        self.assertEqual(rows[child.id]["parent_id"], 1)
        self.assertEqual(rows[child.id]["level"], 2)
        self.assertEqual(rows[1]["image"], "men")

    def test_guest_and_trader_cannot_change_categories(self):
        self.assertEqual(self.client.post("/api/admin/categories/", {"name_ar": "س", "name_en": "X"}, format="json").status_code, 401)
        self.assertEqual(self.client.patch("/api/admin/categories/1/", {"name_en": "Changed"}, format="json").status_code, 401)
        self.client.post("/api/auth/login/", {"username": "trader", "password": "demo123"}, format="json")
        self.assertEqual(self.client.get("/api/admin/categories/").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/categories/", {"name_ar": "س", "name_en": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch("/api/admin/categories/1/", {"name_en": "Changed"}, format="json").status_code, 403)
        self.assertEqual(Category.objects.get(pk=1).name_en, "Men")

    def test_staff_can_create_and_update_a_nested_category(self):
        self.login_staff()
        created = self.client.post(
            "/api/admin/categories/",
            {"name_ar": "قمصان", "name_en": "Shirts", "parent_id": 1},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["parent_id"], 1)
        self.assertEqual(created.data["level"], 2)
        updated = self.client.patch(
            f"/api/admin/categories/{created.data['id']}/",
            {"name_en": "Dress shirts", "parent_id": 2},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["parent_id"], 2)
        self.assertEqual(updated.data["name_ar"], "قمصان")
        self.assertEqual(Product.objects.get(id=1).category_id, 1)
