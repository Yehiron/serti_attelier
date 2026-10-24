from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException, NotFound, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(APIException):
    status_code = 400
    default_code = "validation_error"
    default_detail = _("No se pudo completar la operación.")


class PublicationError(DomainError):
    pass


class PieceNotFound(NotFound):
    default_code = "piece_not_found"
    default_detail = _("No se encontró la pieza.")


def problem_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.messages)
    if isinstance(exc, Http404):
        exc = NotFound()
    if isinstance(exc, PermissionDenied):
        from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied

        exc = DRFPermissionDenied()
    response = exception_handler(exc, context)
    if response is None:
        return None
    code = str(getattr(exc, "default_code", "error"))
    if isinstance(exc, Throttled):
        code = "rate_limited"
    elif isinstance(exc, ValidationError):
        code = "validation_error"
    titles = {
        400: _("Solicitud inválida"),
        403: _("Acceso denegado"),
        404: _("No encontrado"),
        409: _("Conflicto"),
        429: _("Demasiadas solicitudes"),
    }
    response.data = {
        "type": f"{settings.PUBLIC_SITE_URL}/errors/{code}",
        "title": str(titles.get(response.status_code, _("Error"))),
        "status": response.status_code,
        "code": code,
        "detail": problem_detail(response.data),
    }
    response.data.update(getattr(exc, "extra", {}))
    response.content_type = "application/problem+json"
    return response


def problem_detail(data: Any) -> str:
    if isinstance(data, dict):
        return "; ".join(
            f"{field}: {problem_detail(value)}" if field != "detail" else problem_detail(value)
            for field, value in data.items()
        )
    if isinstance(data, list):
        return "; ".join(problem_detail(item) for item in data)
    return str(data)
