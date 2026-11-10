"""Library lifecycle. Frozen generations protect drafts and immutable publications."""

import hashlib
import math
import uuid
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, transaction
from PIL import Image, UnidentifiedImageError

from apps.audit.services import record
from apps.catalog.images import (
    MAX_BYTES,
    build_renditions,
    cap_master,
    encode_webp,
    validated_image,
)

from .documents import require_capability
from .models import DraftRevision, HomePublication, HomeSection, MediaAsset, PageRevision


def ratios():
    from .registry import REGISTRY

    return tuple(
        dict.fromkeys(
            ratio for spec in REGISTRY.values() for slot in spec.slots for ratio in slot.ratios
        )
    )


def validate_adjustments(focal_x, focal_y, crops, width, height):
    def unit(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1

    if not unit(focal_x) or not unit(focal_y):
        raise ValidationError("El punto de interés debe estar dentro de la foto.")
    if not isinstance(crops, dict) or set(crops) - set(ratios()):
        raise ValidationError("Selecciona una proporción disponible.")
    for ratio, box in crops.items():
        if not isinstance(box, dict) or set(box) != {"x", "y", "w", "h"}:
            raise ValidationError("El recorte necesita posición, ancho y alto.")
        if not all(unit(v) for v in box.values()):
            raise ValidationError("El recorte debe estar dentro de la foto.")
        x, y, w, h = (box[k] for k in ("x", "y", "w", "h"))
        a, b = map(int, ratio.split(":"))
        if w <= 0 or h <= 0 or x + w > 1.000001 or y + h > 1.000001:
            raise ValidationError("El recorte debe estar dentro de la foto.")
        if abs(w * width / (h * height) - a / b) > 0.015:
            raise ValidationError("El recorte no coincide con la proporción elegida.")


def upload(upload, actor, request=None, *, audit=True):
    require_capability(actor, "edit")
    if upload.size > MAX_BYTES:
        raise ValidationError("La foto no puede superar 25 MB.")
    # Inspect the actual decoder format, not filename/content_type. Shared decoder
    # enforces pixel/byte limits, real decoding, orientation and metadata removal.
    try:
        clean = validated_image(upload)
    except ValidationError as exc:
        raise ValidationError(
            "No se pudo abrir la foto. Usa JPEG, PNG o WebP, de hasta 25 MB y "
            "40 megapíxeles. SVG y HEIC no se admiten aquí."
        ) from exc
    upload.seek(0)
    try:
        with Image.open(upload) as probe:
            if probe.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Usa JPEG, PNG o WebP. SVG y HEIC no se admiten aquí.")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValidationError("La foto no es válida. Usa JPEG, PNG o WebP.") from exc
    upload.seek(0)
    digest = hashlib.sha256(upload.read()).hexdigest()
    existing = MediaAsset.objects.filter(sha256=digest).first()
    if existing:
        return existing, True
    encoded = encode_webp(clean)
    path = default_storage.save(f"cms/library/originals/{uuid.uuid4().hex}.webp", encoded)
    try:
        with transaction.atomic():
            asset = MediaAsset.objects.create(
                original=path,
                width=clean.width,
                height=clean.height,
                size=encoded.size,
                sha256=digest,
                author=actor,
            )
            if audit:
                record("cms.media_uploaded", actor=actor, obj=asset, request=request)
            transaction.on_commit(lambda: enqueue(asset.pk, asset.version))
        return asset, False
    except IntegrityError:
        default_storage.delete(path)
        return MediaAsset.objects.get(sha256=digest), True


def enqueue(asset_id, version):
    """Queue outages remain recoverable from the library without leaking internals."""
    from .tasks import render_media

    try:
        render_media.delay(asset_id, version)
    except Exception:
        MediaAsset.objects.filter(pk=asset_id, version=version).update(state="failed")


def default_crop(asset, ratio):
    a, b = map(int, ratio.split(":"))
    w = min(1, asset.height * a / b / asset.width)
    h = min(1, asset.width * b / a / asset.height)
    return {
        "x": min(max(asset.focal_x - w / 2, 0), 1 - w),
        "y": min(max(asset.focal_y - h / 2, 0), 1 - h),
        "w": w,
        "h": h,
    }


@transaction.atomic
def render(asset_id, version):
    asset = MediaAsset.objects.select_for_update(of=("self",)).get(pk=asset_id)
    if asset.version != version:
        return
    if str(version) in asset.versions:
        asset.state = "ready"
        asset.save(update_fields=["state"])
        return
    with asset.original.open("rb") as source:
        image = validated_image(source)
    payloads = {}
    for ratio in ratios():
        box = asset.crops.get(ratio) or default_crop(asset, ratio)
        x, y, w, h = (box[k] for k in ("x", "y", "w", "h"))
        cropped = cap_master(
            image.crop(
                (
                    round(x * image.width),
                    round(y * image.height),
                    round((x + w) * image.width),
                    round((y + h) * image.height),
                )
            )
        )
        paths = build_renditions(
            cropped, f"cms/library/renditions/{uuid.uuid4().hex}", (240, 480, 960, 1600, 2400)
        )
        payloads[ratio] = {
            "paths": paths,
            "width": cropped.width,
            "height": cropped.height,
            "alt": {"es": asset.alt_es, "en": asset.alt_en},
            "focal": {"x": asset.focal_x, "y": asset.focal_y},
        }
    asset.versions = {**asset.versions, str(version): payloads}
    asset.state = "ready"
    asset.save(update_fields=["versions", "state", "updated_at"])


def reference(asset, crop):
    ref = {"asset": asset.pk, "crop": crop, "version": asset.version}
    validate_reference(ref, selecting=True)
    return ref


def validate_reference(value, *, selecting=False):
    if (
        not isinstance(value, dict)
        or set(value) != {"asset", "crop", "version"}
        or type(value["asset"]) is not int
        or type(value["version"]) is not int
        or value["crop"] not in ratios()
    ):
        raise ValidationError("Selecciona una foto y un recorte de la biblioteca.")
    rows = MediaAsset.objects
    if connection.in_atomic_block:
        rows = rows.select_for_update(of=("self",))
    asset = rows.filter(pk=value["asset"]).first()
    if not asset or (selecting and asset.archived):
        raise ValidationError("Esta foto está archivada o ya no está disponible.")
    generation = asset.versions.get(str(value["version"]), {}).get(value["crop"])
    if not generation:
        raise ValidationError("La foto se está preparando. Vuelve a intentarlo en unos momentos.")
    if any(not generation["alt"].get(lang, "").strip() for lang in ("es", "en")):
        raise ValidationError(
            "Escribe el texto alternativo en español e inglés antes de usar la foto."
        )
    return deepcopy(value)


def resolve(ref, locale):
    asset = MediaAsset.objects.get(pk=ref["asset"])
    data = deepcopy(asset.versions[str(ref["version"])][ref["crop"]])
    if "paths" in data:
        paths = data.pop("paths")
        data["src"] = default_storage.url(paths.get("960") or paths[max(paths, key=int)])
        data["srcset"] = ", ".join(
            f"{default_storage.url(p)} {w}w"
            for w, p in sorted(paths.items(), key=lambda item: int(item[0]))
        )
    data["alt"] = data["alt"].get(locale) or data["alt"].get("es", "")
    return data


def all_usage():
    """One scan per request, independent of page size. Includes legacy URLs/paths."""
    from .services import section_source

    sources = [
        ("Borrador", str(row), section_source(row))
        for row in HomeSection.objects.prefetch_related("slides")
    ]
    publications = list(HomePublication.objects.all())
    revisions = list(PageRevision.objects.order_by("page_id", "-version"))
    current_pages = {}
    for row in revisions:
        current_pages.setdefault(row.page_id, row.pk)
    for row in publications:
        label = "Publicado" if row.pk == publications[0].pk else "Historial"
        sources.append(
            (label, f"Inicio · publicación {row.pk}", [row.snapshot, row.draft_snapshot])
        )
    for row in revisions:
        sources.append(
            (
                "Publicado" if row.pk in current_pages.values() else "Historial",
                f"Página · publicación {row.pk}",
                row.snapshot,
            )
        )
    for row in DraftRevision.objects.all():
        sources.append(("Historial", f"Restauración {row.pk}", row.snapshot))
    # Personalization services are CMS images but independent from home documents.
    from .models import PersonalizationService

    for row in PersonalizationService.objects.all():
        sources.append(
            (
                "Borrador",
                str(row),
                {"image": row.image.name, "image_reference": row.image_reference},
            )
        )
    return UsageIndex(sources)


class UsageIndex:
    """Flatten snapshots once; look up each asset by ID and path."""

    def __iter__(self):
        return iter(self.sources)

    def __init__(self, sources):
        self.sources = sources
        self.assets = {}
        self.strings = {}

        def walk(value, index):
            if isinstance(value, dict):
                if type(value.get("asset")) is int:
                    self.assets.setdefault(value["asset"], set()).add(index)
                for item in value.values():
                    walk(item, index)
            elif isinstance(value, list):
                for item in value:
                    walk(item, index)
            elif isinstance(value, str):
                for token in {value, *value.replace(",", " ").split()}:
                    self.strings.setdefault(token, set()).add(index)

        for index, (_, _, source) in enumerate(sources):
            walk(source, index)


def used_by(asset, sources):
    paths = {asset.original.name, asset.legacy_key}
    legacy_urls = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "paths":
                    paths.update(item.values())
                if key in {"src", "srcset"} and isinstance(item, str):
                    legacy_urls.update(part.split(" ")[0] for part in item.split(", "))
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(asset.versions)
    paths.discard("")
    urls = {default_storage.url(p) for p in paths} | (legacy_urls - {""})

    if not isinstance(sources, UsageIndex):
        sources = UsageIndex(sources)
    matches = set(sources.assets.get(asset.pk, ()))
    for token in paths | urls:
        matches.update(sources.strings.get(token, ()))
    return [
        {"state": sources.sources[i][0], "label": sources.sources[i][1]} for i in sorted(matches)
    ]


@transaction.atomic
def remove(asset, actor, request=None):
    require_capability(actor, "edit")
    asset = MediaAsset.objects.select_for_update(of=("self",)).get(pk=asset.pk)
    if used_by(asset, all_usage()):
        raise ValidationError(
            "Esta foto se usa en el borrador, la tienda o el historial. Puedes archivarla."
        )
    # Deletion leaves files for the audited, age-gated orphan collector.
    record("cms.media_deleted", actor=actor, obj=asset, request=request)
    asset.delete()
