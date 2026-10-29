from typing import Any, cast

from django.apps import apps
from django.db.models import Field
from django.utils.functional import Promise
from django.utils.translation import override

from apps.catalog.models import Piece


def test_project_fields_have_explicit_spanish_labels() -> None:
    # Technical identifiers and words shared by both languages may match the default.
    shared_names = {"id", "sku", "slug", "error"}
    missing = []
    with override("es"):
        for model in apps.get_models():
            if not model.__module__.startswith("apps."):
                continue
            for field in (*model._meta.concrete_fields, *model._meta.many_to_many):
                if field.auto_created:
                    continue
                label = str(field.verbose_name)
                if (
                    field.name not in shared_names
                    and label.casefold() == field.name.replace("_", " ").casefold()
                ):
                    missing.append(f"{model._meta.label}.{field.name}: {label}")
                assert isinstance(field.verbose_name, Promise), (
                    f"{model._meta.label}.{field.name} must use gettext_lazy"
                )
    assert not missing, "Fields need Spanish verbose_name labels: " + ", ".join(missing)


def test_translated_fields_inherit_spanish_base_labels() -> None:
    with override("es"):
        assert (
            str(cast("Field[Any, Any]", Piece._meta.get_field("name_es")).verbose_name)
            == "Nombre [es]"
        )
        assert (
            str(cast("Field[Any, Any]", Piece._meta.get_field("name_en")).verbose_name)
            == "Nombre [en]"
        )
        assert str(
            cast("Field[Any, Any]", Piece._meta.get_field("short_description_es")).verbose_name
        ) == ("Descripción corta [es]")
