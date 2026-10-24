from celery import shared_task
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from PIL import Image

from .images import encode_webp, validated_image
from .models import PieceImage


@shared_task  # type: ignore[untyped-decorator]  # Celery has no stubs.
def process_piece_image(image_id: int) -> None:
    # Serialize retries and replacements on the same image. Never expose exception details.
    with transaction.atomic():
        obj = PieceImage.objects.select_for_update().filter(pk=image_id).first()
        if obj is None:
            return
        paths: list[str] = []
        try:
            with obj.original.open("rb") as source:
                image = validated_image(source)
            renditions: dict[str, str] = {}
            # Keep a usable source-sized rendition even below the smallest standard width.
            widths = [width for width in (480, 960, 1600, 2400) if width <= image.width]
            if not widths:
                widths = [image.width]
            for width in widths:
                resized = image.resize(
                    (width, max(1, round(image.height * width / image.width))),
                    Image.Resampling.LANCZOS,
                )
                path = default_storage.save(
                    f"pieces/renditions/{obj.pk}/{width}.webp", encode_webp(resized)
                )
                paths.append(path)
                renditions[str(width)] = path
            previous = obj.renditions.get("webp", {}).values()
            obj.renditions = {"webp": renditions}
            obj.width, obj.height = image.size
            obj.processing_status = PieceImage.ProcessingStatus.READY
            obj.error = ""
            obj.save(update_fields=["renditions", "width", "height", "processing_status", "error"])
            for path in previous:
                default_storage.delete(path)
        except Exception:
            for path in paths:
                default_storage.delete(path)
            obj.processing_status = PieceImage.ProcessingStatus.FAILED
            obj.error = str(_("No se pudo procesar la imagen."))
            obj.save(update_fields=["processing_status", "error"])
