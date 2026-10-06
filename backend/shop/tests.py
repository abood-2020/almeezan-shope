from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from shop.models import (
    Category,
    Invoice,
    Order,
    OrderLine,
    PriceList,
    PriceListItem,
    Product,
    SiteSetting,
    Trader,
)


class ShopDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_initial_data")

    def test_product_code_is_unique(self):
        original = Product.objects.get(code="RW-MN-001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    category=original.category,
                    name_ar="نسخة",
                    name_en="Copy",
                    code="RW-MN-001",
                    base_price_ils=Decimal("10.00"),
                    unit_ar="قطعة",
                    unit_en="piece",
                    min_qty=1,
                )

    def test_minimum_quantity_must_be_at_least_one(self):
        product = Product.objects.get(code="RW-MN-001")
        product.min_qty = 0
        with self.assertRaises(ValidationError):
            product.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                product.save()

    def test_category_ids_match_the_frontend_and_skip_all_products(self):
        self.assertEqual(list(Category.objects.values_list("id", "name_en")), [
            (1, "Men"),
            (2, "Women"),
            (3, "Boys"),
            (4, "Girls"),
        ])
        self.assertFalse(Category.objects.filter(name_en="All products").exists())
        self.assertEqual(Product.objects.get(id=1).category_id, 1)
        self.assertEqual(Product.objects.get(id=7).category.name_en, "Girls")

    def test_one_price_row_per_product_and_list(self):
        self.assertEqual(PriceListItem.objects.filter(price_list_id="local").count(), 8)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PriceListItem.objects.create(
                    price_list_id="local",
                    product_id=1,
                    price=Decimal("1.00"),
                )

    def test_prices_cannot_be_negative(self):
        item = PriceListItem.objects.get(price_list_id="export", product_id=1)
        item.price = Decimal("-0.01")
        with self.assertRaises(ValidationError):
            item.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                item.save()

    def test_ils_fallback_and_explicit_foreign_price(self):
        product = Product.objects.get(id=1)
        local = PriceList.objects.get(id="local")
        export = PriceList.objects.get(id="export")
        PriceListItem.objects.get(price_list=local, product=product).delete()
        self.assertEqual(local.price_for(product), product.base_price_ils)
        self.assertEqual(export.price_for(product), Decimal("25.00"))
        PriceListItem.objects.get(price_list=export, product=product).delete()
        self.assertIsNone(export.price_for(product))

    def test_trader_uses_django_user_and_hashed_password(self):
        trader = Trader.objects.get(id="horizon")
        self.assertEqual(trader.user.username, "trader")
        self.assertEqual(trader.user.email, "trader@example.com")
        self.assertTrue(trader.user.check_password("demo123"))
        self.assertNotIn("demo123", trader.user.password)
        self.assertEqual(trader.price_list_id, "local")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Trader.objects.create(
                    id="other",
                    user=trader.user,
                    name_ar="آخر",
                    name_en="Other",
                    price_list_id="local",
                )

    def test_order_status_choices_and_snapshot(self):
        order = Order.objects.get(number="RW-2026-1042")
        self.assertEqual(order.status, Order.Status.REVIEW)
        self.assertEqual(order.trader_id, "horizon")
        self.assertEqual(order.trader_name_ar, "متجر الأفق")
        order.status = "shipped"
        with self.assertRaises(ValidationError):
            order.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                order.save()

    def test_order_line_keeps_submitted_price(self):
        line = OrderLine.objects.get(order__number="RW-2026-1042", product_id=1)
        self.assertEqual(line.unit_price, Decimal("82.00"))
        self.assertEqual(line.option_label, "عاجي / Ivory · M")
        line.product.base_price_ils = Decimal("1.00")
        line.product.save()
        PriceListItem.objects.filter(product=line.product).update(price=Decimal("1.00"))
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("82.00"))

    def test_order_line_quantity_must_be_positive(self):
        line = OrderLine.objects.get(order__number="RW-2026-1021", product_id=7)
        line.quantity = 0
        with self.assertRaises(ValidationError):
            line.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                line.save()

    def test_seed_is_idempotent_and_does_not_reset_password(self):
        before = self._counts()
        user = User.objects.get(username="export")
        user.set_password("changed-password")
        user.save()
        call_command("seed_initial_data")
        self.assertEqual(before, self._counts())
        user.refresh_from_db()
        self.assertTrue(user.check_password("changed-password"))
        self.assertEqual(Invoice.objects.get(number="INV-2026-087").trader_id, "horizon")

    def test_site_setting_is_a_singleton(self):
        SiteSetting.objects.create(company_whatsapp_number="970599123456")
        self.assertEqual(SiteSetting.objects.count(), 1)
        setting = SiteSetting.objects.get()
        self.assertEqual(setting.company_whatsapp_number, "970599123456")
        setting.company_whatsapp_number = "12"
        with self.assertRaises(ValidationError):
            setting.save()
        setting.refresh_from_db()
        with self.assertRaises(ValidationError):
            setting.delete()
        self.assertEqual(SiteSetting.objects.count(), 1)

    def test_string_representations(self):
        self.assertEqual(str(Category.objects.get(id=2)), "Women")
        self.assertIn("RW-WM-003", str(Product.objects.get(id=3)))
        self.assertEqual(str(Trader.objects.get(id="atlas")), "Atlas Trading")
        self.assertEqual(str(Order.objects.get(number="RW-2026-1036")), "RW-2026-1036")
        self.assertEqual(str(Invoice.objects.get(number="INV-2026-087")), "INV-2026-087")
        self.assertEqual(str(PriceList.objects.get(id="export")), "Export traders")

    def _counts(self):
        return (
            Category.objects.count(),
            Product.objects.count(),
            Trader.objects.count(),
            PriceList.objects.count(),
            PriceListItem.objects.count(),
            Order.objects.count(),
            OrderLine.objects.count(),
            Invoice.objects.count(),
        )
