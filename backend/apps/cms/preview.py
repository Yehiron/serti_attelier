from datetime import UTC, datetime

from django.core import signing
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.exceptions import DomainError

MAX_AGE = 600


class PreviewInvalid(DomainError):
    status_code = 403
    default_code = "preview_invalid"
    default_detail = _("La vista previa no es válida o ha caducado.")


def make_token(user: User) -> str:
    if not user.is_active or not user.is_staff:
        raise PreviewInvalid()
    return signing.TimestampSigner(salt="cms-preview").sign(str(user.pk))


def verify_token(token: str) -> User:
    try:
        value = signing.TimestampSigner(salt="cms-preview").unsign(token, max_age=MAX_AGE)
        user = User.objects.get(pk=int(value), is_active=True, is_staff=True)
    except (signing.BadSignature, ValueError, User.DoesNotExist) as exc:
        raise PreviewInvalid() from exc
    return user


def expires_at(token: str) -> str:
    # The signature has already been verified by the caller.
    timestamp = signing.b62_decode(token.rsplit(":", 2)[1])
    return datetime.fromtimestamp(timestamp + MAX_AGE, tz=UTC).isoformat()
