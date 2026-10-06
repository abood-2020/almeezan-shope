from django.urls import include, path

from shop.api.admin_urls import urlpatterns as admin_urlpatterns
from shop.api.views import (
    CategoryListView,
    CsrfView,
    CurrentPricingView,
    InvoiceDetailView,
    InvoiceListView,
    LoginView,
    LogoutView,
    MeView,
    OrderDetailView,
    OrderListCreateView,
    ProductDetailView,
    ProductListView,
    PublicSettingsView,
)

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("catalog/categories/", CategoryListView.as_view(), name="catalog-categories"),
    path("catalog/products/", ProductListView.as_view(), name="catalog-products"),
    path("catalog/products/<int:product_id>/", ProductDetailView.as_view(), name="catalog-product-detail"),
    path("pricing/current/", CurrentPricingView.as_view(), name="pricing-current"),
    path("orders/", OrderListCreateView.as_view(), name="orders"),
    path("orders/<str:order_number>/", OrderDetailView.as_view(), name="order-detail"),
    path("invoices/", InvoiceListView.as_view(), name="invoices"),
    path("invoices/<str:invoice_id>/", InvoiceDetailView.as_view(), name="invoice-detail"),
    path("settings/", PublicSettingsView.as_view(), name="settings"),
    path("admin/", include(admin_urlpatterns)),
]
