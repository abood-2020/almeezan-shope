from django.urls import path

from shop.api.views import (
    CategoryListView,
    CsrfView,
    CurrentPricingView,
    LoginView,
    LogoutView,
    MeView,
    OrderDetailView,
    OrderListCreateView,
    ProductDetailView,
    ProductListView,
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
]
