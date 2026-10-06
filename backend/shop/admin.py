from django.contrib import admin

from .models import (
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


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 0


class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 0


class ProductOptionInline(admin.TabularInline):
    model = ProductOption
    extra = 0


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name_ar", "name_en", "image_key")
    search_fields = ("name_ar", "name_en", "image_key")
    ordering = ("id",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name_en", "category", "base_price_ils", "min_qty", "available")
    search_fields = ("code", "name_ar", "name_en")
    list_filter = ("available", "category")
    ordering = ("id",)
    inlines = [ProductImageInline, ProductColorInline, ProductSizeInline, ProductOptionInline]


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol")
    search_fields = ("code", "name")
    ordering = ("code",)


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("id", "name_en", "currency", "is_active")
    search_fields = ("id", "name_ar", "name_en")
    list_filter = ("currency", "is_active")
    inlines = [PriceListItemInline]


@admin.register(Trader)
class TraderAdmin(admin.ModelAdmin):
    list_display = ("id", "name_en", "username", "email", "price_list", "is_active")
    search_fields = ("id", "name_ar", "name_en", "user__username", "user__email")
    list_filter = ("is_active", "price_list")

    @admin.display(description="Username")
    def username(self, obj):
        return obj.user.username

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "trader_name_ar", "ordered_on", "status", "currency_symbol", "total")
    search_fields = ("number", "trader_name_ar", "trader__id")
    list_filter = ("status", "currency")
    inlines = [OrderLineInline]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "trader", "issued_on", "amount", "file_name")
    search_fields = ("number", "file_name", "trader__id", "trader__name_en")
    list_filter = ("trader",)


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ("company_whatsapp_number",)

    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()
