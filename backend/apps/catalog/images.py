"""Content validation and metadata-free encoding; never trust the upload's MIME or suffix."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000


def validated_image(upload: File[bytes] | BinaryIO) -> Image.Image:
    upload.seek(0)
    data = upload.read(MAX_BYTES + 1)
    upload.seek(0)
    if len(data) > MAX_BYTES:
        raise ValidationError(_("La imagen no puede superar 15 MB."))
    try:
        with Image.open(BytesIO(data)) as image:
            fmt = image.format
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError(_("Usa una imagen JPEG, PNG o WebP."))
            if image.width * image.height > MAX_PIXELS:
                raise ValidationError(_("La imagen no puede superar 40 megapíxeles."))
            # Bytes appended after the image (phone MPF/HDR data, or a polyglot payload) are
            # not rejected: many legitimate phone JPEGs carry them, and the re-encode below
            # stores only decoded pixels, so nothing appended can survive into storage.
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            oriented = ImageOps.exif_transpose(image)
            mode = (
                "RGBA"
                if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info
                else "RGB"
            )
            # A fresh image is essential: convert() alone preserves image.info.
            clean = Image.new(mode, oriented.size)
            clean.paste(oriented.convert(mode))
            return clean
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError(
            _("La imagen es inválida, está incompleta o es demasiado grande.")
        ) from exc


def crop_to_ratio(image: Image.Image, width: int = 16, height: int = 9) -> Image.Image:
    """Center-crop to an exact aspect ratio so owners never need to pre-crop covers."""
    # Whole multiples of the ratio keep it exact (e.g. 1920x1081 -> 1920x1080).
    scale = min(image.width // width, image.height // height)
    if scale == 0:
        raise ValidationError(_("La imagen es demasiado pequeña."))
    target_w, target_h = width * scale, height * scale
    left = (image.width - target_w) // 2
    top = (image.height - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


def encode_webp(image: Image.Image) -> ContentFile[bytes]:
    output = BytesIO()
    image.save(output, format="WEBP", quality=85)
    return ContentFile(output.getvalue())


def validate_upload(upload: File[bytes]) -> None:
    validated_image(upload)
