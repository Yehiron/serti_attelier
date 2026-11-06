import hashlib

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from apps.orders.models import Order


class Command(BaseCommand):
    help = "Activa/consulta contador temporal de lecturas E2E, solo DEBUG."

    def add_arguments(self, parser):
        parser.add_argument("--reference", required=True)
        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Solo disponible con DEBUG=True.")
        order = Order.objects.get(payment_attempts__reference=options["reference"])
        key = "e2e:tracking:" + hashlib.sha256(order.public_token.encode()).hexdigest()
        if options["reset"]:
            cache.set(key, 0, 300)
        self.stdout.write(str(cache.get(key, 0)))
