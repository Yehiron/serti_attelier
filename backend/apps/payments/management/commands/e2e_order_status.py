from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from apps.accounts.models import User
from apps.accounts.roles import PROPIETARIO
from apps.orders.models import Order
from apps.orders.services import transition_status


class Command(BaseCommand):
    help = "Avanza preparación/envío mediante el servicio real, solo DEBUG."

    def add_arguments(self, parser):
        parser.add_argument("--reference", required=True)
        parser.add_argument("--target", choices=["preparing", "shipped"], required=True)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Solo disponible con DEBUG=True.")
        actor = User.objects.filter(username__startswith="e2e-", groups__name=PROPIETARIO).first()
        if actor is None:
            raise CommandError("Crea antes e2e_admin_session.")
        order = Order.objects.get(payment_attempts__reference=options["reference"])
        request = RequestFactory().post("/")
        request.user = actor
        transition_status(
            order,
            "fulfillment_status",
            options["target"],
            request=request,
            expected_status=order.fulfillment_status,
            carrier="Transportadora E2E",
            tracking_number="E2E-123",
            notify=False,
        )
