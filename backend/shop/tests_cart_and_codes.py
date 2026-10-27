from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from shop.fx import publish_rates
from shop.models import CartItem, Category, Currency, PriceList, Product, ProductImage, ProductOption, Trader
from shop.services import generate_product_code, import_products, save_product


class CartPersistenceTests(TestCase):
    def setUp(self):
        publish_rates(timezone.localdate(), {"USD": Decimal("1"), "CNY": Decimal("7.20000000"), "ILS": Decimal("3.60000000")})
        self.category = Category.objects.create(name_ar="ملابس", name_en="Clothing")
        self.currency_ils = Currency.objects.get_or_create(code="ILS", defaults={"name_ar": "شيكل", "name_en": "Shekel", "symbol": "₪", "decimal_places": 2})[0]
        self.currency_usd = Currency.objects.get_or_create(code="USD", defaults={"name_ar": "دولار", "name_en": "Dollar", "symbol": "$", "decimal_places": 2})[0]

        self.price_list = PriceList.objects.create(
            id="cart-test-list",
            name_ar="قائمة تجريبية",
            name_en="Test List",
            currency=self.currency_ils,
            pricing_mode=PriceList.PricingMode.RULE_BASED,
            default_discount_percent=Decimal("0"),
        )

        self.trader_user = User.objects.create_user(username="cart_trader", password="password123")
        self.trader = Trader.objects.create(
            id="cart_trader",
            user=self.trader_user,
            name_ar="تاجر السلة",
            name_en="Cart Trader",
            price_list=self.price_list,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.trader_user)

        self.product1 = Product.objects.create(
            category=self.category,
            name_ar="قميص أزرق",
            name_en="Blue Shirt",
            code="CART-001",
            factory_code="B012-1",
            base_price_ils=Decimal("50.00"),
            base_currency=self.currency_ils,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=2,
            available=True,
        )
        ProductOption.objects.create(product=self.product1, label="M · Blue", is_available=True)

        self.product2 = Product.objects.create(
            category=self.category,
            name_ar="بنطال أسود",
            name_en="Black Pants",
            code="CART-002",
            factory_code="B012-2",
            base_price_ils=Decimal("80.00"),
            base_currency=self.currency_ils,
            unit_ar="قطعة",
            unit_en="piece",
            min_qty=1,
            available=True,
        )
        ProductOption.objects.create(product=self.product2, label="L · Black", is_available=True)

    def test_trader_can_get_and_put_cart(self):
        # Initial empty cart
        res = self.client.get("/api/cart/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["items"]), 0)

        # PUT replace cart items
        put_res = self.client.put(
            "/api/cart/",
            {
                "items": [
                    {"product_id": self.product1.id, "option": "M · Blue", "quantity": 5},
                    {"product_id": self.product2.id, "option": "L · Black", "quantity": 3},
                ]
            },
            format="json",
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(len(put_res.data["items"]), 2)
        self.assertEqual(put_res.data["count"], 8)

        # Query CartItem from DB directly
        db_items = CartItem.objects.filter(trader=self.trader)
        self.assertEqual(db_items.count(), 2)

    def test_cart_merge_merges_guest_items(self):
        # Trader already has product1 x2 in server cart
        CartItem.objects.create(trader=self.trader, product=self.product1, option="M · Blue", quantity=2)

        # Guest cart has product1 x5 (same variant) and product2 x4
        merge_res = self.client.post(
            "/api/cart/merge/",
            {
                "items": [
                    {"product_id": self.product1.id, "option": "M · Blue", "quantity": 5},
                    {"product_id": self.product2.id, "option": "L · Black", "quantity": 4},
                ]
            },
            format="json",
        )
        self.assertEqual(merge_res.status_code, 200)
        items_map = {item["id"]: item["qty"] for item in merge_res.data["items"]}
        # Duplicate product1 gets max quantity (5)
        self.assertEqual(items_map[self.product1.id], 5)
        self.assertEqual(items_map[self.product2.id], 4)

    def test_cart_excludes_archived_products(self):
        CartItem.objects.create(trader=self.trader, product=self.product1, option="M · Blue", quantity=2)
        self.product1.is_archived = True
        self.product1.save()

        res = self.client.get("/api/cart/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["items"]), 0)
        self.assertFalse(CartItem.objects.filter(trader=self.trader, product=self.product1).exists())

    def test_checkout_clears_cart_only_on_success(self):
        CartItem.objects.create(trader=self.trader, product=self.product1, option="M · Blue", quantity=2)

        # Order creation fails due to min quantity constraint
        fail_res = self.client.post(
            "/api/orders/",
            {
                "display_currency": "ILS",
                "items": [{"product_id": self.product1.id, "option": "M · Blue", "qty": 1}],
            },
            format="json",
        )
        self.assertEqual(fail_res.status_code, 400)
        # CartItem MUST still exist after failed checkout
        self.assertTrue(CartItem.objects.filter(trader=self.trader).exists())

        # Successful order creation
        success_res = self.client.post(
            "/api/orders/",
            {
                "display_currency": "ILS",
                "items": [{"product_id": self.product1.id, "option": "M · Blue", "qty": 2, "expected_unit_price": "50.00"}],
            },
            format="json",
        )
        self.assertEqual(success_res.status_code, 201)
        # CartItem MUST be deleted on successful checkout
        self.assertFalse(CartItem.objects.filter(trader=self.trader).exists())


class ProductCodeAndFactoryCodeTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name_ar="أحذية", name_en="Shoes")
        self.currency_ils = Currency.objects.get_or_create(code="ILS", defaults={"name_ar": "شيكل", "name_en": "Shekel", "symbol": "₪", "decimal_places": 2})[0]

    def test_auto_code_generation_is_category_sequential(self):
        code1 = generate_product_code(self.category.id)
        expected_prefix = f"{self.category.id:03d}-"
        self.assertTrue(code1.startswith(expected_prefix))
        self.assertEqual(code1, f"{expected_prefix}00001")

        p1 = Product.objects.create(
            category=self.category,
            name_ar="حذاء 1",
            name_en="Shoe 1",
            code=code1,
            base_price_ils=Decimal("100.00"),
            base_currency=self.currency_ils,
            unit_ar="زوج",
            unit_en="pair",
            min_qty=1,
        )

        code2 = generate_product_code(self.category.id)
        self.assertEqual(code2, f"{expected_prefix}00002")

    def test_save_product_auto_generates_code_when_omitted(self):
        product = save_product({
            "name_ar": "حذاء رياضي",
            "name_en": "Running Shoe",
            "category": self.category,
            "base_price_ils": Decimal("120.00"),
            "base_currency": self.currency_ils,
            "unit_ar": "زوج",
            "unit_en": "pair",
            "min_qty": 1,
            "factory_code": "FACTORY-99",
            "options": ["Default"],
        })
        self.assertTrue(product.code.startswith(f"{self.category.id:03d}-"))
        self.assertEqual(product.factory_code, "FACTORY-99")

        # Code remains immutable when updated, even if category changes
        cat2 = Category.objects.create(name_ar="حقائب", name_en="Bags")
        original_code = product.code
        updated = save_product({
            "category": cat2,
            "name_ar": "حذاء رياضي معدل",
            "factory_code": "FACTORY-99-REV",
            "options": ["Default"],
        }, product=product)

        self.assertEqual(updated.code, original_code)
        self.assertEqual(updated.factory_code, "FACTORY-99-REV")
        self.assertEqual(updated.category_id, cat2.id)


class ExcelImportUpdatesTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name_ar="فساتين", name_en="Dresses")
        self.currency_cny = Currency.objects.get_or_create(code="CNY", defaults={"name_ar": "يوان", "name_en": "Yuan", "symbol": "¥", "decimal_places": 2})[0]
        self.currency_ils = Currency.objects.get_or_create(code="ILS", defaults={"name_ar": "شيكل", "name_en": "Shekel", "symbol": "₪", "decimal_places": 2})[0]

    def test_import_auto_generates_code_and_accepts_new_category_header(self):
        rows = [
            {
                "Code": "",
                "تصنيف المنتج": str(self.category.id),
                "Factory_Code": "DRESS-001",
                "Name_AR": "فستان سهرة",
                "Name_EN": "Evening Dress",
                "Unit_AR": "قطعة",
                "Unit_EN": "piece",
                "Min_Qty": 5,
                "Original_Currency": "CNY",
                "Original_Price": 150,
                "Available": 1,
                "Description_AR": "فستان أنيق",
                "Description_EN": "Elegant dress",
            }
        ]

        imported = import_products(rows, lang="ar")
        self.assertEqual(len(imported), 1)
        product = imported[0]
        self.assertTrue(product.code.startswith(f"{self.category.id:03d}-"))
        self.assertEqual(product.factory_code, "DRESS-001")
        self.assertEqual(product.name_en, "Evening Dress")
