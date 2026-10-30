"""Delete obsolete files only after commit and after checking every durable reference."""

from __future__ import annotations

from typing import Any

from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_save

from apps.cms.models import HeroSlide, HomePublication, HomeSection, PersonalizationService

from .models import Category, Collection, PieceImage, PieceVideo, Stone

IMAGE_MODELS = (
    PieceVideo,
    PieceImage,
    Category,
    Collection,
    Stone,
    HomeSection,
    HeroSlide,
    PersonalizationService,
)


def contains_reference(value: Any, path: str, url: str) -> bool:
    if isinstance(value, str):
        return value in (path, url) or any(part.split(" ")[0] == url for part in value.split(", "))
    if isinstance(value, dict):
        return any(contains_reference(item, path, url) for item in value.values())
    if isinstance(value, list):
        return any(contains_reference(item, path, url) for item in value)
    return False


def file_paths(obj: models.Model) -> set[str]:
    if isinstance(obj, PieceVideo):
        return {str(f.name) for f in (obj.mp4, obj.poster) if f} | set(
            obj.poster_renditions.get("webp", {}).values()
        )
    if isinstance(obj, HeroSlide):
        return (
            ({str(obj.image.name)} if obj.image else set())
            | ({str(obj.image_mobile.name)} if obj.image_mobile else set())
            | set(obj.renditions.get("webp", {}).values())
            | set(obj.mobile_renditions.get("webp", {}).values())
        )
    field = (
        "original"
        if isinstance(obj, PieceImage)
        else ("cover_image" if isinstance(obj, (Category, Collection, Stone)) else "image")
    )
    master = getattr(obj, field)
    renditions = getattr(obj, "cover_renditions", getattr(obj, "renditions", {}))
    return ({master.name} if master else set()) | set(renditions.get("webp", {}).values())


def delete_unreferenced(paths: set[str], using: str) -> None:
    # One pass over the live objects and one over publications, whatever the number of paths.
    candidates = set(paths)
    for model in IMAGE_MODELS:
        for obj in model._default_manager.using(using).iterator():
            candidates -= file_paths(obj)
            if not candidates:
                return
    urls = {path: default_storage.url(path) for path in candidates}
    for publication in HomePublication.objects.using(using).iterator():
        candidates = {
            path
            for path in candidates
            if not (
                contains_reference(publication.snapshot, path, urls[path])
                or contains_reference(publication.draft_snapshot, path, urls[path])
            )
        }
        if not candidates:
            return
    for path in candidates:
        default_storage.delete(path)


def replaced_files(
    sender: type[models.Model], instance: models.Model, using: str, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not instance.pk:
        return
    previous = sender._default_manager.using(using).filter(pk=instance.pk).first()
    if previous is not None:
        private_original_cleanup(previous, instance, using)
        paths = file_paths(previous) - file_paths(instance)
        if paths:
            transaction.on_commit(lambda: delete_unreferenced(paths, using), using=using)


def deleted_files(instance: models.Model, using: str, **kwargs: Any) -> None:
    private_original_cleanup(instance, None, using)
    paths = file_paths(instance)
    if paths:
        transaction.on_commit(lambda: delete_unreferenced(paths, using), using=using)


def register() -> None:
    for model in IMAGE_MODELS:
        pre_save.connect(
            replaced_files, sender=model, dispatch_uid=f"image_replace_{model._meta.label}"
        )
        post_delete.connect(
            deleted_files, sender=model, dispatch_uid=f"image_delete_{model._meta.label}"
        )


def private_original_cleanup(
    previous: models.Model, current: models.Model | None, using: str
) -> None:
    if not isinstance(previous, PieceVideo) or not previous.original:
        return
    if isinstance(current, PieceVideo) and previous.original.name == current.original.name:
        return
    name, storage = str(previous.original.name), previous.original.storage

    def cleanup() -> None:
        if not PieceVideo.objects.using(using).filter(original=name).exists():
            storage.delete(name)

    transaction.on_commit(cleanup, using=using)
