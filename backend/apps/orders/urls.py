from django.urls import path

from .api import AddItemView, CartView, OrderDetailView, OrdersView, QuoteView, RemoveItemView

urlpatterns = [
    path("cart", CartView.as_view(), name="cart"),
    path("cart/items", AddItemView.as_view(), name="cart-add"),
    path("cart/items/<str:sku>", RemoveItemView.as_view(), name="cart-remove"),
    path("checkout/quote", QuoteView.as_view(), name="checkout-quote"),
    path("orders", OrdersView.as_view(), name="orders-create"),
    path("orders/<str:public_token>", OrderDetailView.as_view(), name="orders-detail"),
]
