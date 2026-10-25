from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from shop.models import Category, Currency, Order, OrderLine, PriceList, Product, ProductOption, Trader
from shop.services import create_order, delete_product, restore_product


class ProductDeletionTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name_ar="ملابس", name_en="Clothing")
        self.currency_ils = Currency.objects.get_or_create(code="ILS", defaults={"name_ar": "شيكل", "name_en": "Shekel", "symbol": "₪", "decimal_places": 2})[0]
        self.currency_usd = Currency.objects.get_or_create(code="USD", defaults={"name_ar": "دولار", "name_en": "Dollar", "symbol": "$", "decimal_places": 2})[0]
        self.currency_cny = Currency.objects.get_or_create(code="CNY", defaults={"name_ar": "يوان", "name_en": "Yuan", "symbol": "¥", "decimal_places": 2})[0]

        # Price list
        self.price_list = PriceList.objects.create(
            id="default",
            name_ar="القائمة الافتراضية",
            name_en="Default List",
            currency=self.currency_ils,
            is_default=True,
            is_active=True,
            pricing_mode=PriceList.PricingMode.RULE_BASED,
        )

        # Admin user
        self.admin_user = User.objects.create_user(username="test_admin", password="password123", is_staff=True)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)

        # Trader user
        self.trader_user = User.objects.create_user(username="test_trader", password="password123", is_staff=False)
        self.trader = Trader.objects.create(
            id="test_trader",
            user=self.trader_user,
            name_ar="تاجر تجريبي",
            name_en="Test Trader",
            price_list=self.price_list,
            is_active=True,
        )
        self.trader_client = APIClient()
        self.trader_client.force_authenticate(user=self.trader_user)

        # Unused product (no dependencies)
        self.clean_product = Product.objects.create(
            category=self.category,
            name_ar="منتج نظيف",
            name_en="Clean Product",
            code="RW-CLN-001",
            base_price_ils=Decimal("50.00"),
            base_currency=self.currency_ils,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
            available=True,
        )
        ProductOption.objects.create(product=self.clean_product, label="Default", is_available=True)

        # Product with historical order dependency
        self.ordered_product = Product.objects.create(
            category=self.category,
            name_ar="منتج تاريخي",
            name_en="Historical Product",
            code="RW-HIST-001",
            base_price_ils=Decimal("100.00"),
            base_currency=self.currency_ils,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
            available=True,
        )
        ProductOption.objects.create(product=self.ordered_product, label="Standard", is_available=True)

        # Create an order with ordered_product
        self.order = create_order(
            trader=self.trader,
            note="Test historical order",
            items=[{"product_id": self.ordered_product.id, "option": "Standard", "qty": 2, "price": "100.00"}],
            acknowledge_price_changes=True,
        )

    def test_anonymous_user_cannot_delete_product(self):
        anon_client = APIClient()
        res = anon_client.delete(f"/api/admin/products/{self.clean_product.id}/")
        self.assertEqual(res.status_code, 401)
        self.assertTrue(Product.objects.filter(id=self.clean_product.id).exists())

    def test_ordinary_trader_cannot_delete_product(self):
        res = self.trader_client.delete(f"/api/admin/products/{self.clean_product.id}/")
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Product.objects.filter(id=self.clean_product.id).exists())

    def test_permanent_deletion_of_unused_product(self):
        product_id = self.clean_product.id
        code = self.clean_product.code

        res = self.admin_client.delete(f"/api/admin/products/{product_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "deleted")
        self.assertEqual(res.data["archived"], False)

        # Exists neither in database nor in catalog
        self.assertFalse(Product.objects.filter(id=product_id).exists())

        # Public catalog no longer has this product
        catalog_res = self.client.get("/api/catalog/products/")
        product_ids = [p["id"] for p in catalog_res.data]
        self.assertNotIn(product_id, product_ids)

        # Code can be reused safely
        recreated = Product.objects.create(
            category=self.category,
            name_ar="منتج بديل",
            name_en="Replacement Product",
            code=code,
            base_price_ils=Decimal("40.00"),
            base_currency=self.currency_ils,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
            available=True,
        )
        self.assertEqual(recreated.code, code)

    def test_archival_of_product_with_order_history(self):
        product_id = self.ordered_product.id
        order_total_before = self.order.total
        line = self.order.lines.first()
        line_price_before = line.unit_price

        res = self.admin_client.delete(f"/api/admin/products/{product_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "archived")
        self.assertEqual(res.data["archived"], True)

        # Product is soft-deleted/archived in DB
        self.ordered_product.refresh_from_db()
        self.assertTrue(self.ordered_product.is_archived)

        # Historical order data is completely unchanged
        self.order.refresh_from_db()
        self.assertEqual(self.order.total, order_total_before)
        line.refresh_from_db()
        self.assertEqual(line.unit_price, line_price_before)
        self.assertEqual(line.product_id, product_id)

        # Public catalog does NOT show the archived product
        catalog_res = self.client.get("/api/catalog/products/")
        product_ids = [p["id"] for p in catalog_res.data]
        self.assertNotIn(product_id, product_ids)

        # Public detail view returns 404
        detail_res = self.client.get(f"/api/catalog/products/{product_id}/")
        self.assertEqual(detail_res.status_code, 404)

    def test_checkout_rejects_archived_product(self):
        # Archive the product
        delete_product(self.ordered_product)
        self.ordered_product.refresh_from_db()
        self.assertTrue(self.ordered_product.is_archived)

        # Try to order it
        order_res = self.trader_client.post(
            "/api/orders/",
            {
                "display_currency": "ILS",
                "items": [{"product_id": self.ordered_product.id, "option": "Standard", "qty": 1, "price": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(order_res.status_code, 400)
        self.assertIn("items", order_res.data)
        self.assertIn("no longer available", order_res.data["items"][0])

    def test_restore_archived_product(self):
        delete_product(self.ordered_product)
        self.ordered_product.refresh_from_db()
        self.assertTrue(self.ordered_product.is_archived)

        # Restore via admin API
        restore_res = self.admin_client.post(f"/api/admin/products/{self.ordered_product.id}/restore/")
        self.assertEqual(restore_res.status_code, 200)
        self.assertFalse(restore_res.data["is_archived"])

        self.ordered_product.refresh_from_db()
        self.assertFalse(self.ordered_product.is_archived)

        # Now reappears in public catalog
        catalog_res = self.client.get("/api/catalog/products/")
        product_ids = [p["id"] for p in catalog_res.data]
        self.assertIn(self.ordered_product.id, product_ids)

    def test_admin_list_filtering_by_archived(self):
        # Clean product is active, ordered_product is archived
        delete_product(self.ordered_product)

        # Default list (active only)
        res_default = self.admin_client.get("/api/admin/products/")
        ids_default = [p["id"] for p in res_default.data]
        self.assertIn(self.clean_product.id, ids_default)
        self.assertNotIn(self.ordered_product.id, ids_default)

        # Archived only
        res_archived = self.admin_client.get("/api/admin/products/?archived=true")
        ids_archived = [p["id"] for p in res_archived.data]
        self.assertNotIn(self.clean_product.id, ids_archived)
        self.assertIn(self.ordered_product.id, ids_archived)

        # All products
        res_all = self.admin_client.get("/api/admin/products/?archived=all")
        ids_all = [p["id"] for p in res_all.data]
        self.assertIn(self.clean_product.id, ids_all)
        self.assertIn(self.ordered_product.id, ids_all)
