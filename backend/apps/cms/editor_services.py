"""Draft mutations for the visual editor, retaining the existing image pipelines."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils.translation import gettext as _

from apps.audit.services import record
from apps.catalog.images import validated_image

from . import services
from .documents import draft_mutation
from .models import HeroSlide, HomeSection


def validate_order(actual: list[int], ordered: list[int]) -> None:
    if len(ordered) != len(set(ordered)) or set(actual) != set(ordered):
        raise ValidationError(
            _("El orden no corresponde a las fotos o secciones actuales. Recarga la página.")
        )


@draft_mutation(lambda *args: "home")
@transaction.atomic
def reorder_sections(ordered: list[int], actor=None, request=None) -> None:
    rows = {row.pk: row for row in HomeSection.objects.select_for_update(of=("self",))}
    validate_order(list(rows), ordered)
    before = [str(row) for row in sorted(rows.values(), key=lambda row: (row.position, row.pk))]
    for position, pk in enumerate(ordered):
        rows[pk].position = position
        rows[pk].save(update_fields=["position"])
    after = [str(rows[pk]) for pk in ordered]
    if before != after:
        record(
            "cms.sections_reordered",
            actor=actor,
            request=request,
            diff={"Orden de las secciones": [" → ".join(before), " → ".join(after)]},
        )


@draft_mutation(lambda *args: "home")
@transaction.atomic
def reorder_hero_slides(
    section: HomeSection, device: str, ordered: list[int], actor=None, request=None
) -> None:
    HomeSection.objects.select_for_update(of=("self",)).get(pk=section.pk)
    rows = {
        row.pk: row for row in section.slides.select_for_update(of=("self",)).filter(device=device)
    }
    validate_order(list(rows), ordered)
    before = [str(row) for row in sorted(rows.values(), key=lambda row: (row.position, row.pk))]
    for position, pk in enumerate(ordered):
        rows[pk].position = position
        rows[pk].save(update_fields=["position"])
    after = [str(rows[pk]) for pk in ordered]
    if before != after:
        record(
            "cms.slides_reordered",
            actor=actor,
            request=request,
            obj=section,
            diff={"Orden de las fotos": [" → ".join(before), " → ".join(after)]},
        )


@draft_mutation(lambda *args: "home")
@transaction.atomic
def set_section_visibility(section: HomeSection, visible: bool, actor=None, request=None) -> None:
    section = HomeSection.objects.select_for_update(of=("self",)).get(pk=section.pk)
    section.is_visible = visible
    services.save_section(section, actor=actor, request=request)


@draft_mutation(lambda *args: "home")
@transaction.atomic
def replace_section_image(
    section: HomeSection, upload: UploadedFile[bytes], actor=None, request=None
) -> None:
    if section.kind not in {"story", "personalize", "banner"}:
        raise ValidationError(_("Esta sección no admite una foto."))
    section = HomeSection.objects.select_for_update(of=("self",)).get(pk=section.pk)
    section.image = upload
    for locale in ("es", "en"):
        if not getattr(section, f"image_alt_{locale}"):
            setattr(section, f"image_alt_{locale}", section.title_es or _("Foto SERTI"))
    services.save_section(section, actor=actor, request=request)


@draft_mutation(lambda *args: "home")
@transaction.atomic
def upload_hero_photos(
    section: HomeSection, device: str, uploads: list[UploadedFile[bytes]], actor=None, request=None
) -> list[str]:
    if section.kind != "hero" or device not in HeroSlide.Device.values or not uploads:
        raise ValidationError(_("Selecciona una portada, un dispositivo y al menos una foto."))
    HomeSection.objects.select_for_update(of=("self",)).get(pk=section.pk)
    warnings = []
    # Validate the complete batch before generating any stored files.
    for upload in uploads:
        image = validated_image(upload)
        if (device == "desktop" and image.width < image.height) or (
            device == "mobile" and image.width > image.height
        ):
            warnings.append(
                _("La orientación de una foto no coincide con el dispositivo seleccionado.")
            )
    last = section.slides.filter(device=device).order_by("-position").first()
    start = last.position + 1 if last else 0
    labels = []
    for position, upload in enumerate(uploads, start=start):
        alt = _("Portada SERTI %(position)s") % {"position": position + 1}
        labels.append(str(alt))
        slide = HeroSlide(
            section=section,
            device=device,
            position=position,
            image=upload,
            alt_es=alt,
            alt_en=alt,
        )
        services.save_hero_slide(slide, actor=actor, request=request, audit=False)
    record(
        "cms.slides_uploaded",
        actor=actor,
        request=request,
        obj=section,
        diff={"Fotos de portada": ["", ", ".join(labels)]},
    )
    return warnings
