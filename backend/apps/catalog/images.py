"""Content validation and metadata-free encoding; never trust the upload's MIME or suffix."""

from __future__ import annotations

import importlib
import warnings
from io import BytesIO
from typing import BinaryIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

# Optional decoder: register once; JPEG/PNG/WebP/AVIF remain usable without it.
try:
    importlib.import_module("pillow_heif").register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 40_000_000


def validated_image(upload: File[bytes] | BinaryIO) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        return _validated_image(upload)


def _validated_image(upload: File[bytes] | BinaryIO) -> Image.Image:
    upload.seek(0)
    data = upload.read(MAX_BYTES + 1)
    upload.seek(0)
    if len(data) > MAX_BYTES:
        raise ValidationError(_("La imagen no puede superar 25 MB."))
    try:
        with Image.open(BytesIO(data)) as image:
            fmt = image.format
            if fmt not in {"JPEG", "PNG", "WEBP", "AVIF", "HEIF", "HEIC"}:
                raise ValidationError(_("Usa una imagen JPEG, PNG, WebP, AVIF o HEIC (iPhone)."))
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
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
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
    image.save(output, format="WEBP", quality=82, method=6)
    return ContentFile(output.getvalue())


def validate_upload(upload: File[bytes]) -> None:
    validated_image(upload)


def cap_master(image: Image.Image) -> Image.Image:
    """Bound storage cost without ever enlarging an upload."""
    result = image.copy()
    result.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    return result


def build_renditions(
    image: Image.Image,
    prefix: str,
    widths: tuple[int, ...] = (480, 960, 1600, 2400),
) -> dict[str, str]:
    paths: dict[str, str] = {}
    try:
        for width in [value for value in widths if value <= image.width] or [image.width]:
            resized = image.resize(
                (width, max(1, round(image.height * width / image.width))),
                Image.Resampling.LANCZOS,
            )
            paths[str(width)] = default_storage.save(f"{prefix}/{width}.webp", encode_webp(resized))
    except Exception:
        for path in paths.values():
            default_storage.delete(path)
        raise
    return paths
