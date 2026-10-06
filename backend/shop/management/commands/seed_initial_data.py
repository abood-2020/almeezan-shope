from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from shop.models import (
    Category,
    Currency,
    Invoice,
    Order,
    OrderLine,
    PriceList,
    PriceListItem,
    Product,
    ProductColor,
    ProductImage,
    ProductOption,
    ProductSize,
    SiteSetting,
    Trader,
)

# Copied from app/data.ts, app/pricing.ts, and the initial state in app/page.tsx.
# Category index 0 ("All products") is not a real category.

CATEGORIES = [
    {"id": 1, "name_ar": "رجالي", "name_en": "Men", "image_key": "men"},
    {"id": 2, "name_ar": "نسائي", "name_en": "Women", "image_key": "women"},
    {"id": 3, "name_ar": "أولاد", "name_en": "Boys", "image_key": "boys"},
    {"id": 4, "name_ar": "بناتي", "name_en": "Girls", "image_key": "girls"},
]

PRODUCTS = [
    {
        "id": 1, "name_ar": "قميص رجالي كتان بقصّة مريحة", "name_en": "Relaxed linen shirt",
        "code": "RW-MN-001", "category_id": 1, "base_price_ils": "82", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 12, "available": True, "image_key": "men-shirt", "badge": "الأكثر طلبًا",
        "description_ar": "قميص كتان ناعم بقصّة مريحة وتفاصيل بسيطة، مناسب لتشكيلة الملابس اليومية.",
        "description_en": "A soft linen shirt with a relaxed fit and clean detailing for everyday assortments.",
        "colors": [
            {"name_ar": "عاجي", "name_en": "Ivory", "hex": "#e9e5d8"},
            {"name_ar": "رملي", "name_en": "Sand", "hex": "#bb9c79", "image_key": "men-shirt-sand"},
            {"name_ar": "كحلي", "name_en": "Navy", "hex": "#22364c", "image_key": "men-shirt-navy"},
        ],
        "sizes": ["S", "M", "L", "XL"],
    },
    {
        "id": 2, "name_ar": "تيشيرت رجالي قطني أساسي", "name_en": "Essential cotton tee",
        "code": "RW-MN-002", "category_id": 1, "base_price_ils": "45", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 24, "available": True, "image_key": "men-tee-white", "badge": "جديد",
        "description_ar": "تيشيرت قطني عملي بقصّة منتظمة ولمسة ناعمة، قطعة أساسية لكل موسم.",
        "description_en": "A regular-fit cotton tee with a soft hand feel, an easy staple for every season.",
        "colors": [
            {"name_ar": "أبيض", "name_en": "White", "hex": "#f5f2ea"},
            {"name_ar": "أسود", "name_en": "Black", "hex": "#24262a", "image_key": "men-tee-black"},
            {"name_ar": "وردي هادئ", "name_en": "Dusty rose", "hex": "#bd8a90", "image_key": "men-tee-rose"},
        ],
        "sizes": ["S", "M", "L", "XL"],
    },
    {
        "id": 3, "name_ar": "بليزر نسائي بقصّة انسيابية", "name_en": "Tailored relaxed blazer",
        "code": "RW-WM-003", "category_id": 2, "base_price_ils": "155", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 6, "available": True, "image_key": "women-blazer", "badge": "اختيار رِواق",
        "description_ar": "بليزر نسائي بخطوط انسيابية وقصّة مريحة، سهل التنسيق مع الإطلالات العملية.",
        "description_en": "An easy tailored blazer with fluid lines, designed for versatile workwear styling.",
        "colors": [
            {"name_ar": "رملي", "name_en": "Sand", "hex": "#c7ac91"},
            {"name_ar": "أسود", "name_en": "Black", "hex": "#26272a", "image_key": "women-blazer-black"},
        ],
        "sizes": ["S", "M", "L"],
    },
    {
        "id": 4, "name_ar": "فستان نسائي ميدي ناعم", "name_en": "Soft midi dress",
        "code": "RW-WM-004", "category_id": 2, "base_price_ils": "112", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 8, "available": True, "image_key": "women-dress-berry", "badge": "جديد",
        "description_ar": "فستان ميدي بتصميم هادئ وتفاصيل أنيقة للاستخدام اليومي والمناسبات البسيطة.",
        "description_en": "A quietly elegant midi dress for everyday wear and understated occasions.",
        "colors": [
            {"name_ar": "توتي", "name_en": "Berry", "hex": "#8f456d"},
            {"name_ar": "عاجي", "name_en": "Ivory", "hex": "#eee5dc", "image_key": "women-dress"},
        ],
        "sizes": ["S", "M", "L"],
    },
    {
        "id": 5, "name_ar": "طقم أولاد قطني مريح", "name_en": "Boys cotton two-piece set",
        "code": "RW-BY-005", "category_id": 3, "base_price_ils": "76", "unit_ar": "طقم", "unit_en": "set",
        "min_qty": 12, "available": True, "image_key": "boys-set-blue", "badge": "",
        "description_ar": "طقم قطني مكون من قطعتين بقصّة مريحة تتحمل حركة اليوم.",
        "description_en": "A comfortable two-piece cotton set made for everyday movement.",
        "colors": [
            {"name_ar": "أزرق فاتح", "name_en": "Pale blue", "hex": "#a6bdc8"},
            {"name_ar": "رملي", "name_en": "Sand", "hex": "#c9b69b", "image_key": "boys-set-sand"},
        ],
        "sizes": ["4Y", "6Y", "8Y", "10Y"],
    },
    {
        "id": 6, "name_ar": "بنطال رجالي بقصّة مستقيمة", "name_en": "Straight-leg tailored trousers",
        "code": "RW-MN-006", "category_id": 1, "base_price_ils": "98", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 12, "available": False, "image_key": "men-trousers", "badge": "",
        "description_ar": "بنطال بقصّة مستقيمة وتفاصيل نظيفة للتنسيق اليومي.",
        "description_en": "Clean straight-leg trousers for versatile everyday styling.",
        "colors": [
            {"name_ar": "رملي", "name_en": "Sand", "hex": "#baa587"},
            {"name_ar": "كحلي", "name_en": "Navy", "hex": "#30465b", "image_key": "men-trousers-navy"},
        ],
        "sizes": ["S", "M", "L", "XL"],
    },
    {
        "id": 7, "name_ar": "فستان بناتي بتفاصيل ناعمة", "name_en": "Girls gathered dress",
        "code": "RW-GR-007", "category_id": 4, "base_price_ils": "88", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 12, "available": True, "image_key": "girls-dress-pink", "badge": "جديد",
        "description_ar": "فستان بناتي بقصّة مريحة وتفاصيل لطيفة تناسب تشكيلة الموسم.",
        "description_en": "A comfortable gathered dress with delicate details for the season.",
        "colors": [
            {"name_ar": "وردي", "name_en": "Pink", "hex": "#d7a5b6"},
            {"name_ar": "عاجي", "name_en": "Ivory", "hex": "#e9decf", "image_key": "girls-dress-ivory"},
        ],
        "sizes": ["4Y", "6Y", "8Y", "10Y"],
    },
    {
        "id": 8, "name_ar": "كارديغان بناتي محبوك", "name_en": "Girls knit cardigan",
        "code": "RW-GR-008", "category_id": 4, "base_price_ils": "73", "unit_ar": "قطعة", "unit_en": "piece",
        "min_qty": 12, "available": True, "image_key": "girls-cardigan", "badge": "",
        "description_ar": "كارديغان خفيف بنسيج ناعم، قطعة سهلة التنسيق مع الإطلالات اليومية.",
        "description_en": "A lightweight soft-knit cardigan, easy to layer with everyday outfits.",
        "colors": [
            {"name_ar": "عاجي", "name_en": "Ivory", "hex": "#e9e0ce"},
            {"name_ar": "توتي", "name_en": "Berry", "hex": "#a46d8a", "image_key": "girls-cardigan-berry"},
        ],
        "sizes": ["4Y", "6Y", "8Y", "10Y"],
    },
]

CURRENCIES = [
    {"code": "ILS", "name": "شيكل / Shekel", "symbol": "₪"},
    {"code": "USD", "name": "دولار أمريكي / US Dollar", "symbol": "$"},
]

EXPORT_PRICES = {1: "25", 2: "14", 3: "47", 4: "34", 5: "23", 6: "30", 7: "27", 8: "22"}

TRADERS = [
    {
        "id": "horizon", "username": "trader", "email": "trader@example.com",
        "name_ar": "متجر الأفق", "name_en": "Horizon Store", "price_list_id": "local", "is_active": True,
    },
    {
        "id": "atlas", "username": "export", "email": "export@example.com",
        "name_ar": "أطلس للتجارة", "name_en": "Atlas Trading", "price_list_id": "export", "is_active": True,
    },
]

ORDERS = [
    {
        "number": "RW-2026-1042", "ordered_on": date(2026, 9, 24), "status": "review",
        "trader_name_ar": "متجر الأفق", "note": "يرجى التواصل لتأكيد الطلب.", "total": "1914", "symbol": "₪",
        "lines": [
            {"product_id": 1, "option_label": "عاجي / Ivory · M", "quantity": 12, "unit_price": "82"},
            {"product_id": 3, "option_label": "رملي / Sand · M", "quantity": 6, "unit_price": "155"},
        ],
    },
    {
        "number": "RW-2026-1036", "ordered_on": date(2026, 9, 18), "status": "confirmed",
        "trader_name_ar": "متجر الأفق", "note": "", "total": "2688", "symbol": "₪",
        "lines": [
            {"product_id": 4, "option_label": "توتي / Berry · M", "quantity": 24, "unit_price": "112"},
        ],
    },
    {
        "number": "RW-2026-1021", "ordered_on": date(2026, 9, 10), "status": "complete",
        "trader_name_ar": "متجر الأفق", "note": "", "total": "1056", "symbol": "₪",
        "lines": [
            {"product_id": 7, "option_label": "وردي / Pink · 6Y", "quantity": 12, "unit_price": "88"},
        ],
    },
]


class Command(BaseCommand):
    help = "Load the current frontend demo catalog, traders, orders, and invoice. Safe to run again."

    @transaction.atomic
    def handle(self, *args, **options):
        for row in CATEGORIES:
            Category.objects.update_or_create(
                id=row["id"],
                defaults={"name_ar": row["name_ar"], "name_en": row["name_en"], "image_key": row["image_key"]},
            )

        for row in CURRENCIES:
            Currency.objects.update_or_create(code=row["code"], defaults={"name": row["name"], "symbol": row["symbol"]})

        for row in PRODUCTS:
            product, _ = Product.objects.update_or_create(
                id=row["id"],
                defaults={
                    "category_id": row["category_id"],
                    "name_ar": row["name_ar"],
                    "name_en": row["name_en"],
                    "code": row["code"],
                    "base_price_ils": Decimal(row["base_price_ils"]),
                    "unit_ar": row["unit_ar"],
                    "unit_en": row["unit_en"],
                    "min_qty": row["min_qty"],
                    "available": row["available"],
                    "description_ar": row["description_ar"],
                    "description_en": row["description_en"],
                    "badge": row["badge"],
                },
            )
            ProductImage.objects.update_or_create(
                product=product,
                image_key=row["image_key"],
                defaults={"sort_order": 0, "is_primary": True},
            )
            colors = {}
            for index, color in enumerate(row["colors"]):
                obj, _ = ProductColor.objects.update_or_create(
                    product=product,
                    name_en=color["name_en"],
                    defaults={
                        "name_ar": color["name_ar"],
                        "hex_code": color["hex"],
                        "image_key": color.get("image_key", ""),
                        "sort_order": index,
                    },
                )
                colors[color["name_en"]] = obj
            sizes = {}
            for index, value in enumerate(row["sizes"]):
                obj, _ = ProductSize.objects.update_or_create(
                    product=product,
                    value=value,
                    defaults={"sort_order": index},
                )
                sizes[value] = obj
            sort_order = 0
            for color in row["colors"]:
                for value in row["sizes"]:
                    label = ProductOption.label_for(color["name_ar"], color["name_en"], value)
                    ProductOption.objects.update_or_create(
                        product=product,
                        label=label,
                        defaults={
                            "color": colors[color["name_en"]],
                            "size": sizes[value],
                            "is_available": True,
                            "sort_order": sort_order,
                        },
                    )
                    sort_order += 1

        local, _ = PriceList.objects.update_or_create(
            id="local",
            defaults={"name_ar": "تجار فلسطين", "name_en": "Palestine traders", "currency_id": "ILS", "is_active": True},
        )
        export, _ = PriceList.objects.update_or_create(
            id="export",
            defaults={"name_ar": "تجار التصدير", "name_en": "Export traders", "currency_id": "USD", "is_active": True},
        )
        for product in Product.objects.all():
            PriceListItem.objects.update_or_create(
                price_list=local,
                product=product,
                defaults={"price": product.base_price_ils},
            )
        for product_id, price in EXPORT_PRICES.items():
            PriceListItem.objects.update_or_create(
                price_list=export,
                product_id=product_id,
                defaults={"price": Decimal(price)},
            )

        traders = {}
        for row in TRADERS:
            user, created = User.objects.get_or_create(username=row["username"], defaults={"email": row["email"]})
            if created:
                user.set_password("demo123")
            user.email = row["email"]
            user.is_active = row["is_active"]
            user.save()
            trader, _ = Trader.objects.update_or_create(
                id=row["id"],
                defaults={
                    "user": user,
                    "name_ar": row["name_ar"],
                    "name_en": row["name_en"],
                    "price_list_id": row["price_list_id"],
                    "is_active": row["is_active"],
                },
            )
            traders[row["name_ar"]] = trader

        symbol_to_code = {row["symbol"]: row["code"] for row in CURRENCIES}
        for row in ORDERS:
            order, _ = Order.objects.update_or_create(
                number=row["number"],
                defaults={
                    "trader": traders[row["trader_name_ar"]],
                    "trader_name_ar": row["trader_name_ar"],
                    "ordered_on": row["ordered_on"],
                    "status": row["status"],
                    "currency_id": symbol_to_code[row["symbol"]],
                    "currency_symbol": row["symbol"],
                    "note": row["note"],
                    "total": Decimal(row["total"]),
                },
            )
            for line in row["lines"]:
                product = Product.objects.get(id=line["product_id"])
                OrderLine.objects.update_or_create(
                    order=order,
                    product=product,
                    option_label=line["option_label"],
                    defaults={
                        "product_code": product.code,
                        "product_name_ar": product.name_ar,
                        "product_name_en": product.name_en,
                        "quantity": line["quantity"],
                        "unit_price": Decimal(line["unit_price"]),
                    },
                )

        Invoice.objects.update_or_create(
            number="INV-2026-087",
            defaults={
                "trader_id": "horizon",
                "issued_on": date(2026, 9, 12),
                "amount": Decimal("456"),
                "file_name": "INV-2026-087.pdf",
                "file_ref": "/files/invoice-demo.pdf",
            },
        )
        SiteSetting.objects.update_or_create(pk=1, defaults={"company_whatsapp_number": ""})

        self.stdout.write(self.style.SUCCESS(
            "Seed complete: "
            f"{Category.objects.count()} categories, "
            f"{Product.objects.count()} products, "
            f"{Trader.objects.count()} traders, "
            f"{Order.objects.count()} orders, "
            f"{Invoice.objects.count()} invoices."
        ))
