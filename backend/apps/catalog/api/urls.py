from django.urls import path

from .views import PieceDetailView, PieceListView, PieceStatusView, TaxonomyView

urlpatterns = [
    path("taxonomy", TaxonomyView.as_view(), name="catalog-taxonomy"),
    path("pieces", PieceListView.as_view(), name="catalog-pieces"),
    path("pieces/status", PieceStatusView.as_view(), name="catalog-status"),
    path("pieces/<slug:slug>", PieceDetailView.as_view(), name="catalog-detail"),
]
