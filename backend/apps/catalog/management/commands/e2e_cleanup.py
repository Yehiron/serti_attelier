"""Remove explicitly marked E2E fixtures without touching mixed orders."""

from typing import Any

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from apps.accounts.models import User
from apps.cart.models import CartItem
from apps.catalog.image_cleanup import batch_file_cleanup
from apps.catalog.models import (
    Collection,
    CollectionPiece,
    Material,
    Piece,
    PieceImage,
    PieceRelation,
    PieceVideo,
)
from apps.cms.models import MediaAsset
from apps.inquiries.models import ContactInquiry
from apps.inventory.models import PieceReservation, PieceStatusChange
from apps.notifications.models import (
    AdminNotification,
    AdminNotificationReceipt,
    NotificationDelivery,
)
from apps.orders.models import Order, OrderIncident, OrderItem, OrderNote, OrderStatusChange
from apps.payments.models import PaymentAttempt, PaymentEvent
from apps.promotions.models import CouponRedemption


class Command(BaseCommand):
    help = "Elimina datos E2E inequívocos (solo DEBUG)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("e2e_cleanup solo funciona con DEBUG activo.")
        with transaction.atomic(), batch_file_cleanup():
            all_pieces = Piece.objects.filter(sku__startswith="E2E-")
            # A hard-deleted E2E piece leaves its lines with piece=NULL and only the SKU snapshot.
            e2e_line = Q(piece__sku__startswith="E2E-") | Q(
                piece__isnull=True, sku__startswith="E2E-"
            )
            candidates = Order.objects.filter(
                pk__in=OrderItem.objects.filter(e2e_line).values("order_id")
            )
            mixed = candidates.filter(pk__in=OrderItem.objects.exclude(e2e_line).values("order_id"))
            mixed_ids = list(mixed.values_list("pk", flat=True))
            self.stdout.write(f"Pedidos mixtos conservados: {mixed_ids}")
            orders = candidates.exclude(pk__in=mixed_ids)
            order_ids = list(orders.values_list("pk", flat=True))
            # A piece in a mixed order, or a reservation for another order, must survive.
            protected_ids = OrderItem.objects.filter(order_id__in=mixed_ids).values("piece_id")
            other_reservations = (
                PieceReservation.objects.filter(order__isnull=False)
                .exclude(order_id__in=order_ids)
                .values("piece_id")
            )
            pieces = all_pieces.exclude(pk__in=protected_ids).exclude(pk__in=other_reservations)
            piece_ids = list(pieces.values_list("pk", flat=True))
            steps = [
                (
                    "mensajes de prueba",
                    ContactInquiry.objects.filter(email__iendswith="@e2e.invalid"),
                ),
                (
                    "recepciones de avisos",
                    AdminNotificationReceipt.objects.filter(notification__order_id__in=order_ids),
                ),
                ("avisos", AdminNotification.objects.filter(order_id__in=order_ids)),
                ("notificaciones", NotificationDelivery.objects.filter(order_id__in=order_ids)),
                ("eventos de pago", PaymentEvent.objects.filter(order_id__in=order_ids)),
                ("intentos de pago", PaymentAttempt.objects.filter(order_id__in=order_ids)),
                ("canjes", CouponRedemption.objects.filter(order_id__in=order_ids)),
                ("incidencias", OrderIncident.objects.filter(order_id__in=order_ids)),
                ("notas", OrderNote.objects.filter(order_id__in=order_ids)),
                ("cambios de pedido", OrderStatusChange.objects.filter(order_id__in=order_ids)),
                ("líneas de pedido", OrderItem.objects.filter(order_id__in=order_ids)),
                (
                    "reservas",
                    PieceReservation.objects.filter(
                        Q(piece_id__in=piece_ids) | Q(order_id__in=order_ids)
                    ),
                ),
                ("pedidos", Order.objects.filter(pk__in=order_ids)),
                ("líneas de carrito", CartItem.objects.filter(piece_id__in=piece_ids)),
                ("piezas en colecciones", CollectionPiece.objects.filter(piece_id__in=piece_ids)),
                (
                    "relaciones",
                    PieceRelation.objects.filter(
                        Q(source_id__in=piece_ids) | Q(target_id__in=piece_ids)
                    ),
                ),
                ("piedras", Piece.stones.through.objects.filter(piece_id__in=piece_ids)),
                ("materiales", Piece.materials.through.objects.filter(piece_id__in=piece_ids)),
                ("cambios de pieza", PieceStatusChange.objects.filter(piece_id__in=piece_ids)),
            ]
            for label, queryset in steps:
                self.stdout.write(f"{label}: {queryset._raw_delete(queryset.db)}")
            for label, queryset in (
                ("fotos", PieceImage.objects.filter(piece_id__in=piece_ids)),
                ("videos", PieceVideo.objects.filter(piece_id__in=piece_ids)),
                ("piezas", Piece.objects.filter(pk__in=piece_ids)),
            ):
                count = queryset.count()
                queryset.delete()
                self.stdout.write(f"{label}: {count}")

            # Only collections marked by this E2E test and left without real pieces.
            collections = Collection.objects.filter(
                slug_es__regex=r"^e2e-coleccion-[0-9]+$"
            ).exclude(
                pk__in=CollectionPiece.objects.exclude(piece__sku__startswith="E2E-").values(
                    "collection_id"
                )
            )
            self.stdout.write(f"colecciones: {collections.delete()[0]}")

            materials = Material.objects.filter(slug_es__regex=r"^e2e-material-[0-9]+$").exclude(
                pieces__isnull=False
            )
            self.stdout.write(f"materiales de prueba: {materials.delete()[0]}")

            # cms-phase4 uploads covers named «Portada de prueba <ms>». Publication history keeps
            # referencing them, so they cannot be deleted; archiving hides them from the library.
            test_media = MediaAsset.objects.filter(
                alt_es__regex=r"^Portada de prueba [0-9]+$", archived=False
            )
            self.stdout.write(f"fotos de prueba archivadas: {test_media.update(archived=True)}")

            users = User.objects.filter(
                username__regex=r"^e2e-[0-9a-f]{32}$", email__endswith="@e2e.invalid"
            )
            user_ids = set(str(pk) for pk in users.values_list("pk", flat=True))
            session_keys = [
                session.pk
                for session in Session.objects.iterator()
                if str(session.get_decoded().get(SESSION_KEY)) in user_ids
            ]
            self.stdout.write(
                f"sesiones: {Session.objects.filter(pk__in=session_keys).delete()[0]}"
            )
            deleted = 0
            for user in users:
                try:
                    with transaction.atomic():
                        user.delete()
                    deleted += 1
                except ProtectedError:
                    self.stdout.write(f"Usuario conservado por referencias: {user.username}")
            self.stdout.write(f"usuarios: {deleted}")
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write("Simulación revertida")
