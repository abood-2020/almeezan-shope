import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

HEX_VALIDATOR = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a HEX color like #22364C.")
CURRENCY_CODE_VALIDATOR = RegexValidator(r"^[A-Za-z]{3}$", "Currency code must be 3 letters.")


class Category(models.Model):
    """Catalog category. A category may nest under another, up to three levels."""

    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    sort_order = models.PositiveIntegerField(default=0)
    image_key = models.CharField(max_length=255, blank=True)
    image = models.FileField(upload_to="categories/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_en

    def clean(self):
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})
        seen = {self.pk} if self.pk else set()
        current = self.parent_id
        depth = 1
        while current:
            if current in seen:
                raise ValidationError({"parent": "This parent would create a circular category."})
            seen.add(current)
            current = Category.objects.filter(pk=current).values_list("parent_id", flat=True).first()
            depth += 1
            if depth > 12:
                raise ValidationError({"parent": "This parent would create a circular category."})
        if depth > 3:
            raise ValidationError({"parent": "Categories cannot be nested more than three levels."})
        if self.pk and depth + _descendant_depth(self.pk) > 3:
            raise ValidationError({
                "parent": "Moving this category would place a descendant below level 3.",
            })
        errors = {}
        siblings = Category.objects.filter(parent_id=self.parent_id)
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)
        if self.name_ar and siblings.filter(name_ar=self.name_ar).exists():
            errors["name_ar"] = "A category with this Arabic name already exists under the same parent."
        if self.name_en and siblings.filter(name_en=self.name_en).exists():
            errors["name_en"] = "A category with this English name already exists under the same parent."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not kwargs.get("raw"):
            self.full_clean()
        return super().save(*args, **kwargs)


def _descendant_depth(category_id, seen=None):
    """Levels that exist below this category. A leaf returns 0."""
    seen = set() if seen is None else seen
    if category_id in seen:
        return 0
    seen.add(category_id)
    child_ids = list(Category.objects.filter(parent_id=category_id).values_list("id", flat=True))
    if not child_ids:
        return 0
    return 1 + max(_descendant_depth(child_id, seen) for child_id in child_ids)


def category_descendant_ids(category_id):
    """The category itself plus every descendant, for product filtering."""
    found = []
    frontier = [category_id]
    seen = set()
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        found.append(current)
        frontier.extend(Category.objects.filter(parent_id=current).values_list("id", flat=True))
    return found


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
    base_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    base_currency = models.ForeignKey(
        "Currency",
        on_delete=models.PROTECT,
        related_name="priced_products",
        default="ILS",
    )
    original_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    original_currency = models.ForeignKey(
        "Currency",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="original_products",
    )
    price_review_required = models.BooleanField(default=False)
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
            models.CheckConstraint(
                check=models.Q(base_price_usd__isnull=True) | models.Q(base_price_usd__gte=0),
                name="product_usd_base_price_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(original_price__isnull=True) | models.Q(original_price__gte=0),
                name="product_original_price_gte_0",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(original_price__isnull=True, original_currency__isnull=True)
                    | models.Q(original_price__isnull=False, original_currency__isnull=False)
                ),
                name="product_original_price_and_currency_together",
            ),
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
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
    )

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
    class PricingMode(models.TextChoices):
        LEGACY = "legacy", "Legacy fixed prices"
        RULE_BASED = "rule_based", "Discount rules"

    class DiscountScope(models.TextChoices):
        ALL = "all", "All products"
        CATEGORIES = "categories", "Selected categories"

    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="price_lists")
    is_active = models.BooleanField(default=True)
    pricing_mode = models.CharField(max_length=16, choices=PricingMode.choices, default=PricingMode.LEGACY)
    default_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    discount_scope = models.CharField(max_length=16, choices=DiscountScope.choices, default=DiscountScope.ALL)
    scope_categories = models.ManyToManyField(Category, blank=True, related_name="scoped_price_lists")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(default_discount_percent__gte=0) & models.Q(default_discount_percent__lte=100),
                name="price_list_discount_between_0_and_100",
            ),
            models.CheckConstraint(
                check=models.Q(pricing_mode__in=["legacy", "rule_based"]),
                name="price_list_pricing_mode_known",
            ),
            models.CheckConstraint(
                check=models.Q(discount_scope__in=["all", "categories"]),
                name="price_list_discount_scope_known",
            ),
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="one_default_price_list",
            ),
        ]

    def clean(self):
        if self.default_discount_percent < 0 or self.default_discount_percent > 100:
            raise ValidationError({"default_discount_percent": "Discount must be between 0 and 100."})
        if self.pricing_mode == self.PricingMode.RULE_BASED and self.currency_id not in ("ILS", "USD"):
            raise ValidationError({"currency": "A discount price list uses ILS or USD."})
        if self.is_default:
            if self.pricing_mode != self.PricingMode.RULE_BASED:
                raise ValidationError({"is_default": "The default price list must use discount rules."})
            if self.default_discount_percent != 0:
                raise ValidationError({"is_default": "The default price list must use a 0% discount."})
            if not self.is_active:
                raise ValidationError({"is_default": "The default price list must stay active."})

    def price_for(self, product):
        """Legacy lists keep stored prices. Rule lists use the shared pricing engine."""
        if self.pricing_mode == self.PricingMode.RULE_BASED:
            from shop.pricing import unit_price

            return unit_price(self, product)
        prefetched = getattr(product, "_prefetched_objects_cache", {}).get("price_list_items")
        if prefetched is not None:
            item = next((row for row in prefetched if row.price_list_id == self.id), None)
        else:
            item = self.items.filter(product=product).first()
        if item is not None:
            return item.price
        if self.currency_id == "ILS" and getattr(product, "base_currency_id", "ILS") in (None, "ILS"):
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


class PriceListCategoryRule(models.Model):
    """Percentage discount for one category inside a rule-based price list."""

    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="category_rules")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="price_rules")
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_list_id", "category_id"]
        constraints = [
            models.UniqueConstraint(fields=["price_list", "category"], name="unique_category_rule_per_list"),
            models.CheckConstraint(
                check=models.Q(discount_percent__gte=0) & models.Q(discount_percent__lte=100),
                name="category_rule_discount_between_0_and_100",
            ),
        ]

    def __str__(self):
        return f"{self.price_list_id} {self.category_id} {self.discount_percent}%"


class PriceListProductRule(models.Model):
    """Percentage discount for one product. It replaces category and default discounts."""

    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="product_rules")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_rules")
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_list_id", "product_id"]
        constraints = [
            models.UniqueConstraint(fields=["price_list", "product"], name="unique_product_rule_per_list"),
            models.CheckConstraint(
                check=models.Q(discount_percent__gte=0) & models.Q(discount_percent__lte=100),
                name="product_rule_discount_between_0_and_100",
            ),
        ]

    def __str__(self):
        return f"{self.price_list_id} {self.product_id} {self.discount_percent}%"


class ExchangeRate(models.Model):
    """Manual directed rate: 1 source currency unit equals `rate` target currency units."""

    source = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="rates_from")
    target = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="rates_to")
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_id", "target_id"]
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_directed_exchange_rate"),
            models.CheckConstraint(check=models.Q(rate__gt=0), name="exchange_rate_positive"),
            models.CheckConstraint(check=~models.Q(source=models.F("target")), name="exchange_rate_not_same_currency"),
        ]

    def clean(self):
        if self.source_id and self.target_id and self.source_id == self.target_id:
            raise ValidationError({"target": "Choose a different target currency. Same-currency prices need no rate."})
        if self.rate is None or self.rate <= 0:
            raise ValidationError({"rate": "Exchange rate must be greater than zero."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"1 {self.source_id} = {self.rate} {self.target_id}"


class RateSnapshot(models.Model):
    """One complete USD-based rate set. Only a full, validated set becomes current."""

    provider = models.CharField(max_length=40, default="frankfurter")
    provider_date = models.DateField()
    fetched_at = models.DateTimeField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-provider_date", "-fetched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="one_current_rate_snapshot",
            ),
        ]

    def __str__(self):
        return f"{self.provider} {self.provider_date}"


class RateSnapshotLine(models.Model):
    """1 USD equals `usd_rate` units of `currency`. USD itself is stored as 1."""

    snapshot = models.ForeignKey(RateSnapshot, on_delete=models.CASCADE, related_name="lines")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="snapshot_lines")
    usd_rate = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta:
        ordering = ["currency_id"]
        constraints = [
            models.UniqueConstraint(fields=["snapshot", "currency"], name="unique_snapshot_currency"),
            models.CheckConstraint(check=models.Q(usd_rate__gt=0), name="snapshot_usd_rate_positive"),
        ]

    def __str__(self):
        return f"1 USD = {self.usd_rate} {self.currency_id}"


class FxRefreshLock(models.Model):
    """Single row used to stop overlapping refreshes from publishing partial rates."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    updated_at = models.DateTimeField(auto_now=True)


class RateObservation(models.Model):
    """One published USD rate date. Pricing snapshots and order history stay separate."""

    provider = models.CharField(max_length=40, default="frankfurter")
    provider_date = models.DateField()
    fetched_at = models.DateTimeField()
    cny_per_usd = models.DecimalField(max_digits=18, decimal_places=8)
    ils_per_usd = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta:
        ordering = ["-provider_date", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "provider_date"], name="unique_fx_daily_observation"),
            models.CheckConstraint(check=models.Q(cny_per_usd__gt=0), name="fx_observation_cny_positive"),
            models.CheckConstraint(check=models.Q(ils_per_usd__gt=0), name="fx_observation_ils_positive"),
        ]
        indexes = [
            models.Index(fields=["provider_date"], name="fx_observation_date_idx"),
        ]

    def __str__(self):
        return f"{self.provider} {self.provider_date}"


class Trader(models.Model):
    id = models.CharField(max_length=32, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="trader")
    name_ar = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160)
    price_list = models.ForeignKey(PriceList, on_delete=models.PROTECT, related_name="traders")
    phone = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=80, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name_en


class TraderCategoryDiscount(models.Model):
    """A discount for one trader and one category. It does not change a shared price list."""

    trader = models.ForeignKey(Trader, on_delete=models.CASCADE, related_name="category_discounts")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="trader_discounts")
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    class Meta:
        ordering = ["trader_id", "category_id"]
        constraints = [
            models.UniqueConstraint(fields=["trader", "category"], name="unique_trader_category_discount"),
            models.CheckConstraint(
                check=models.Q(discount_percent__gte=0) & models.Q(discount_percent__lte=100),
                name="trader_category_discount_between_0_and_100",
            ),
        ]

    def __str__(self):
        return f"{self.trader_id} {self.category_id} {self.discount_percent}%"


class GoogleAccount(models.Model):
    """Google subject bound to one trader user. The ID token itself is never stored."""

    sub = models.CharField(max_length=255, unique=True)
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="google_account")
    email = models.EmailField()
    profile_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.email


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
    rate_snapshot = models.ForeignKey(
        RateSnapshot, null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    rate_provider = models.CharField(max_length=40, blank=True, default="")
    rate_provider_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    price_list_name_ar = models.CharField(max_length=160, blank=True, default="")
    price_list_name_en = models.CharField(max_length=160, blank=True, default="")
    trader_name_en = models.CharField(max_length=160, blank=True, default="")
    trader_email = models.CharField(max_length=254, blank=True, default="")
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
    unit_ar = models.CharField(max_length=40, blank=True, default="")
    unit_en = models.CharField(max_length=40, blank=True, default="")
    category_path_ar = models.CharField(max_length=400, blank=True, default="")
    category_path_en = models.CharField(max_length=400, blank=True, default="")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_currency = models.CharField(max_length=3, blank=True, default="")
    original_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, blank=True, default="")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    pricing_note = models.CharField(max_length=160, blank=True, default="")
    line_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

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
    name_ar = models.CharField(max_length=80, default="رِواق")
    name_en = models.CharField(max_length=80, default="Riwaq")
    tagline_ar = models.CharField(max_length=160, default="مساحة واحدة. فرص تجارية أوسع.")
    tagline_en = models.CharField(max_length=160, default="One place. A world of business possibilities.")
    header_caption_ar = models.CharField(max_length=80, default="تجارة الجملة")
    header_caption_en = models.CharField(max_length=80, default="RIWAQ · WHOLESALE")
    logo = models.FileField(upload_to="brand/", blank=True)
    logo_alt_ar = models.CharField(max_length=120, blank=True, default="")
    logo_alt_en = models.CharField(max_length=120, blank=True, default="")
    favicon = models.FileField(upload_to="brand/", blank=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address_ar = models.CharField(max_length=240, blank=True, default="")
    address_en = models.CharField(max_length=240, blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")
    facebook_url = models.URLField(blank=True, default="")
    seo_title_ar = models.CharField(max_length=120, default="رِواق | أزياء الجملة للتجار")
    seo_title_en = models.CharField(max_length=120, default="Riwaq | Wholesale fashion for traders")
    seo_description_ar = models.TextField(
        blank=True,
        default="اكتشف تشكيلة رِواق للملابس بالجملة، راجع الألوان والمقاسات وأرسل طلبك التجاري.",
    )
    seo_description_en = models.TextField(
        blank=True,
        default="Explore Riwaq wholesale fashion, review colors and sizes, and send your trade request.",
    )
    og_image = models.FileField(upload_to="brand/", blank=True)
    hero_video = models.FileField(upload_to="brand/video/", blank=True)
    hero_video_url = models.URLField(blank=True, default="")
    hero_poster = models.FileField(upload_to="brand/", blank=True)
    footer_explore_ar = models.CharField(max_length=80, default="اكتشف رِواق")
    footer_explore_en = models.CharField(max_length=80, default="Explore Riwaq")
    footer_account_ar = models.CharField(max_length=80, default="حسابك وطلباتك")
    footer_account_en = models.CharField(max_length=80, default="Your account & orders")
    copyright_ar = models.CharField(max_length=80, default="رِواق للتجارة")
    copyright_en = models.CharField(max_length=80, default="Riwaq Trade")
    footer_note_ar = models.CharField(max_length=80, default="مصمم لتجارة أبسط")
    footer_note_en = models.CharField(max_length=80, default="Made for simpler business")
    footer_place_ar = models.CharField(max_length=80, default="فلسطين · العالم")
    footer_place_en = models.CharField(max_length=80, default="Palestine · Worldwide")
    nav_labels = models.JSONField(default=dict, blank=True)
    content_initialized = models.BooleanField(default=False)
    social_links_migrated = models.BooleanField(default=False)

    class Meta:
        verbose_name = "site setting"
        verbose_name_plural = "site settings"
        constraints = [
            models.CheckConstraint(check=models.Q(id=1), name="site_setting_singleton"),
        ]

    def clean(self):
        from shop.content import clean_site_setting

        clean_site_setting(self)

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


class StoreSocialLink(models.Model):
    site = models.ForeignKey(SiteSetting, on_delete=models.CASCADE, related_name="social_links")
    name = models.CharField(max_length=80)
    url = models.URLField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class HomepageSection(models.Model):
    key = models.CharField(max_length=32, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    eyebrow_ar = models.CharField(max_length=120, blank=True, default="")
    eyebrow_en = models.CharField(max_length=120, blank=True, default="")
    title_ar = models.CharField(max_length=200, blank=True, default="")
    title_en = models.CharField(max_length=200, blank=True, default="")
    body_ar = models.TextField(blank=True, default="")
    body_en = models.TextField(blank=True, default="")
    cta_ar = models.CharField(max_length=80, blank=True, default="")
    cta_en = models.CharField(max_length=80, blank=True, default="")
    cta_target = models.CharField(max_length=32, blank=True, default="")
    secondary_cta_ar = models.CharField(max_length=80, blank=True, default="")
    secondary_cta_en = models.CharField(max_length=80, blank=True, default="")
    secondary_cta_target = models.CharField(max_length=32, blank=True, default="")
    aside_title_ar = models.CharField(max_length=200, blank=True, default="")
    aside_title_en = models.CharField(max_length=200, blank=True, default="")
    aside_body_ar = models.TextField(blank=True, default="")
    aside_body_en = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.key


class HomepageBlock(models.Model):
    section = models.ForeignKey(HomepageSection, on_delete=models.CASCADE, related_name="blocks")
    key = models.CharField(max_length=40)
    sort_order = models.PositiveIntegerField(default=0)
    title_ar = models.CharField(max_length=200, blank=True, default="")
    title_en = models.CharField(max_length=200, blank=True, default="")
    body_ar = models.CharField(max_length=400, blank=True, default="")
    body_en = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["section", "key"], name="unique_homepage_block_key"),
        ]

    def __str__(self):
        return f"{self.section.key}:{self.key}"


class ContentPage(models.Model):
    key = models.CharField(max_length=32, unique=True)
    eyebrow_ar = models.CharField(max_length=120, blank=True, default="")
    eyebrow_en = models.CharField(max_length=120, blank=True, default="")
    title_ar = models.CharField(max_length=200, blank=True, default="")
    title_en = models.CharField(max_length=200, blank=True, default="")
    body_ar = models.TextField(blank=True, default="")
    body_en = models.TextField(blank=True, default="")
    intro_title_ar = models.CharField(max_length=200, blank=True, default="")
    intro_title_en = models.CharField(max_length=200, blank=True, default="")
    intro_body_ar = models.TextField(blank=True, default="")
    intro_body_en = models.TextField(blank=True, default="")
    cta_ar = models.CharField(max_length=80, blank=True, default="")
    cta_en = models.CharField(max_length=80, blank=True, default="")
    faq_eyebrow_ar = models.CharField(max_length=120, blank=True, default="")
    faq_eyebrow_en = models.CharField(max_length=120, blank=True, default="")
    faq_title_ar = models.CharField(max_length=200, blank=True, default="")
    faq_title_en = models.CharField(max_length=200, blank=True, default="")
    faq_intro_ar = models.CharField(max_length=300, blank=True, default="")
    faq_intro_en = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class ContentBlock(models.Model):
    page = models.ForeignKey(ContentPage, on_delete=models.CASCADE, related_name="blocks")
    key = models.CharField(max_length=40)
    sort_order = models.PositiveIntegerField(default=0)
    title_ar = models.CharField(max_length=200, blank=True, default="")
    title_en = models.CharField(max_length=200, blank=True, default="")
    body_ar = models.CharField(max_length=400, blank=True, default="")
    body_en = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["page", "key"], name="unique_content_block_key"),
        ]

    def __str__(self):
        return f"{self.page.key}:{self.key}"


class FaqItem(models.Model):
    question_ar = models.CharField(max_length=240)
    question_en = models.CharField(max_length=240)
    answer_ar = models.TextField()
    answer_en = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.question_en
