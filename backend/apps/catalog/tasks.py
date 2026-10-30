from __future__ import annotations

from uuid import uuid4

from celery import shared_task
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .images import build_renditions, validated_image
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
            renditions = build_renditions(image, f"pieces/renditions/{obj.pk}/{uuid4().hex}")
            paths.extend(renditions.values())
            obj.renditions = {"webp": renditions}
            obj.width, obj.height = image.size
            obj.processing_status = PieceImage.ProcessingStatus.READY
            obj.error = ""
            obj.save(update_fields=["renditions", "width", "height", "processing_status", "error"])
        except Exception:
            for path in paths:
                default_storage.delete(path)
            obj.processing_status = PieceImage.ProcessingStatus.FAILED
            obj.error = str(_("No se pudo procesar la imagen."))
            obj.save(update_fields=["processing_status", "error"])


@shared_task  # type: ignore[untyped-decorator]  # Celery has no stubs.
def process_piece_video(video_id: int) -> None:
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from django.core.files import File

    from .images import cap_master, encode_webp
    from .models import PieceVideo
    from .videos import poster_command, probe, transcode_command, video_metadata

    with transaction.atomic():
        obj = PieceVideo.objects.select_for_update().filter(pk=video_id).first()
        if obj is None or (obj.processing_status == "ready" and not obj.original):
            return
        paths: list[str] = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                source, output, poster = (
                    Path(directory) / name for name in ("input", "video.mp4", "poster.png")
                )
                with obj.original.open("rb") as upload, source.open("wb") as target:
                    shutil.copyfileobj(upload, target)
                video_metadata(probe(str(source)))
                subprocess.run(  # noqa: S603 — generated argument list, no shell.
                    transcode_command(str(source), str(output)),
                    timeout=600,
                    check=True,
                    capture_output=True,
                )
                width, height, duration = video_metadata(probe(str(output)))
                subprocess.run(  # noqa: S603 — generated argument list, no shell.
                    poster_command(str(output), str(poster), duration),
                    timeout=60,
                    check=True,
                    capture_output=True,
                )
                with poster.open("rb") as frame:
                    image = cap_master(validated_image(frame))
                prefix = f"pieces/videos/{uuid4().hex}"
                with output.open("rb") as encoded:
                    mp4 = default_storage.save(f"{prefix}/video.mp4", File(encoded))
                paths.append(mp4)
                master = default_storage.save(f"{prefix}/poster.webp", encode_webp(image))
                paths.append(master)
                renditions = build_renditions(image, f"{prefix}/poster")
                paths.extend(renditions.values())
                obj.mp4, obj.poster = mp4, master
                obj.poster_renditions = {"webp": renditions}
                obj.width, obj.height, obj.duration_seconds = width, height, duration
                obj.processing_status, obj.error = "ready", ""
                obj.original = ""
                obj.save()
        except Exception:
            for path in paths:
                default_storage.delete(path)
            obj.processing_status, obj.error = "failed", str(_("No se pudo procesar el video."))
            obj.save(update_fields=["processing_status", "error", "updated_at"])
