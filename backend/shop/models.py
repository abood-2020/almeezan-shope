import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

HEX_VALIDATOR = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a HEX color like #22364C.")
CURRENCY_CODE_VALIDATOR = RegexValidator(r"^[A-Za-z]{3}$", "Currency code must be 3 letters.")


class Category(models.Model):
    """Real catalog category. Frontend index 0 (All products) is not stored."""

    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    image_key = models.CharField(max_length=255, blank=True)
    image = models.FileField(upload_to="categories/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_en


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200)
    code = models.CharField(max_length=64, unique=True)
    base_price_ils = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit_ar = models.CharField(max_length=40)
    unit_en = models.CharField(max_length=40)
    min_qty = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    available = models.BooleanField(default=True)
    description_ar = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    badge = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=models.Q(min_qty__gte=1), name="product_min_qty_gte_1"),
            models.CheckConstraint(check=models.Q(base_price_ils__gte=0), name="product_base_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name_en}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image_key = models.CharField(max_length=255, blank=True)
    image = models.FileField(upload_to="products/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="one_primary_image_per_product",
            ),
        ]

    def __str__(self):
        role = "cover" if self.is_primary else "image"
        return f"{self.product.code} {role}"


class ProductColor(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="colors")
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    hex_code = models.CharField(max_length=7, validators=[HEX_VALIDATOR])
    image_key = models.CharField(max_length=255, blank=True)
    image = models.FileField(upload_to="product-colors/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name_ar"], name="unique_color_ar_per_product"),
            models.UniqueConstraint(fields=["product", "name_en"], name="unique_color_en_per_product"),
        ]

    def save(self, *args, **kwargs):
        if self.hex_code:
            self.hex_code = self.hex_code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name_en} ({self.hex_code})"


class ProductSize(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sizes")
    value = models.CharField(max_length=20)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "value"], name="unique_size_per_product"),
        ]

    def __str__(self):
        return self.value


class ProductOption(models.Model):
    """Sellable choice. Either a color/size pair or a free-text option."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=200)
    color = models.ForeignKey(ProductColor, null=True, blank=True, on_delete=models.SET_NULL, related_name="options")
    size = models.ForeignKey(ProductSize, null=True, blank=True, on_delete=models.SET_NULL, related_name="options")
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "label"], name="unique_option_label_per_product"),
        ]

    def clean(self):
        if self.color_id and self.product_id and self.color.product_id != self.product_id:
            raise ValidationError({"color": "Color belongs to another product."})
        if self.size_id and self.product_id and self.size.product_id != self.product_id:
            raise ValidationError({"size": "Size belongs to another product."})

    @staticmethod
    def label_for(color_ar, color_en, size):
        return f"{color_ar} / {color_en} · {size}"

    def __str__(self):
        return self.label


class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True, validators=[CURRENCY_CODE_VALIDATOR])
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=8)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "currencies"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} {self.symbol}"


class PriceList(models.Model):
    id = models.CharField(max_length=32, primary_key=True)
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="price_lists")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def price_for(self, product):
        """ILS lists fall back to the product base price. Other currencies do not."""
        prefetched = getattr(product, "_prefetched_objects_cache", {}).get("price_list_items")
        if prefetched is not None:
            item = next((row for row in prefetched if row.price_list_id == self.id), None)
        else:
            item = self.items.filter(product=product).first()
        if item is not None:
            return item.price
        if self.currency_id == "ILS":
            return product.base_price_ils
        return None

    def __str__(self):
        return self.name_en


class PriceListItem(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_list_items")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["price_list_id", "product_id"]
        constraints = [
            models.UniqueConstraint(fields=["price_list", "product"], name="unique_price_per_list_product"),
            models.CheckConstraint(check=models.Q(price__gte=0), name="price_list_item_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.price_list_id} {self.product.code} {self.price}"


class Trader(models.Model):
    id = models.CharField(max_length=32, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="trader")
    name_ar = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160)
    price_list = models.ForeignKey(PriceList, on_delete=models.PROTECT, related_name="traders")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name_en


class Order(models.Model):
    class Status(models.TextChoices):
        REVIEW = "review", "Under review"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETE = "complete", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=32, unique=True)
    trader = models.ForeignKey(Trader, on_delete=models.PROTECT, related_name="orders")
    trader_name_ar = models.CharField(max_length=160)
    ordered_on = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REVIEW)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="orders")
    currency_symbol = models.CharField(max_length=8)
    note = models.TextField(blank=True)
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_on", "-number"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=["review", "confirmed", "complete", "cancelled"]),
                name="order_status_known",
            ),
            models.CheckConstraint(check=models.Q(total__gte=0), name="order_total_gte_0"),
        ]

    def __str__(self):
        return self.number


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_lines")
    product_code = models.CharField(max_length=64)
    product_name_ar = models.CharField(max_length=200)
    product_name_en = models.CharField(max_length=200, blank=True)
    option_label = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "option_label", "product"], name="unique_order_line_option"),
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="order_line_qty_gte_1"),
            models.CheckConstraint(check=models.Q(unit_price__gte=0), name="order_line_unit_price_gte_0"),
        ]

    def __str__(self):
        return f"{self.product_code} × {self.quantity}"


class Invoice(models.Model):
    number = models.CharField(max_length=32, unique=True)
    trader = models.ForeignKey(Trader, on_delete=models.PROTECT, related_name="invoices")
    issued_on = models.DateField()
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    file = models.FileField(upload_to="invoices/", blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_ref = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_on", "number"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gte=0), name="invoice_amount_gte_0"),
        ]

    def __str__(self):
        return self.number


class SiteSetting(models.Model):
    company_whatsapp_number = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        verbose_name = "site setting"
        verbose_name_plural = "site settings"
        constraints = [
            models.CheckConstraint(check=models.Q(id=1), name="site_setting_singleton"),
        ]

    def clean(self):
        digits = re.sub(r"\D", "", self.company_whatsapp_number or "")
        if digits and not 8 <= len(digits) <= 15:
            raise ValidationError(
                {"company_whatsapp_number": "Use 8 to 15 digits, or leave the number empty."}
            )
        self.company_whatsapp_number = digits

    def save(self, *args, **kwargs):
        self.pk = 1
        if SiteSetting.objects.filter(pk=1).exists():
            self._state.adding = False
            kwargs.pop("force_insert", None)
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Site settings cannot be deleted.")

    def __str__(self):
        return "Site settings"
