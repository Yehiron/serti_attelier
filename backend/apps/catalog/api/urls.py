from django.urls import path

from .views import (
    CatalogExistsView,
    PieceDetailView,
    PieceListView,
    PieceStatusView,
    TaxonomyView,
    WishlistStatusView,
)

urlpatterns = [
    path("exists", CatalogExistsView.as_view(), name="catalog-exists"),
    path("taxonomy", TaxonomyView.as_view(), name="catalog-taxonomy"),
    path("pieces", PieceListView.as_view(), name="catalog-pieces"),
    path("pieces/wishlist-status", WishlistStatusView.as_view(), name="catalog-wishlist-status"),
    path("pieces/status", PieceStatusView.as_view(), name="catalog-status"),
    path("pieces/<slug:slug>", PieceDetailView.as_view(), name="catalog-detail"),
]
