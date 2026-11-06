from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

ATTRIBUTE_FIELDS = (
    "metal",
    "metal_purity",
    "ring_size",
    "length_mm",
    "dimensions_mm",
    "weight_g",
    "carats",
)


def validate_attributes(value: object) -> None:
    schema: dict[str, tuple[type, ...]] = {
        "ring_size": (str, int, float),
        "length_mm": (int, float),
        "metal": (str,),
        "metal_purity": (str,),
        "carats": (int, float),
        "weight_g": (int, float),
        "dimensions_mm": (str,),
    }
    if not isinstance(value, dict) or any(
        key not in schema or isinstance(item, bool) or not isinstance(item, schema[key])
        for key, item in value.items()
    ):
        raise ValidationError(_("Los atributos contienen claves o tipos no permitidos."))
