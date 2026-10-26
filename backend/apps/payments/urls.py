from django.urls import path

from .api import PaymentAttemptsView, PaymentSyncView, wompi_events

urlpatterns = [
    path("payments/wompi/events", wompi_events, name="wompi-events"),
    path(
        "orders/<str:public_token>/payment-attempts",
        PaymentAttemptsView.as_view(),
        name="payment-attempts",
    ),
    path("orders/<str:public_token>/payment-sync", PaymentSyncView.as_view(), name="payment-sync"),
]
