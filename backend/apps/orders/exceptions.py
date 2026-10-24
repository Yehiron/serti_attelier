from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import DomainError


class CheckoutError(DomainError):
    status_code = 422

    def __init__(self, code: str, *, status: int = 422, **extra: Any) -> None:
        self.default_code = code
        self.status_code = status
        errors = extra.get("errors")
        if isinstance(errors, dict):
            extra["errors"] = flatten_errors(errors)
        self.extra = extra
        super().__init__(_("No se pudo completar la compra."), code=code)


def flatten_errors(errors: dict[str, Any], prefix: str = "") -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, value in errors.items():
        field = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten_errors(value, field))
        else:
            result[field] = (
                [str(message) for message in value] if isinstance(value, list) else [str(value)]
            )
    return result
