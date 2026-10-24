from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.core.http import client_ip

from .models import AuditLog


@transaction.atomic
def record(
    action: str,
    *,
    actor: User | AnonymousUser | None = None,
    obj: models.Model | None = None,
    diff: dict[str, list[object]] | None = None,
    request: HttpRequest | None = None,
) -> AuditLog:
    actor = actor if isinstance(actor, User) else None
    return AuditLog.objects.create(
        action=action,
        actor=actor,
        actor_repr=actor.get_username() if actor else "",
        content_type=ContentType.objects.get_for_model(obj) if obj is not None else None,
        object_id=str(obj.pk) if obj is not None else None,
        object_repr=str(obj)[:300] if obj is not None else None,
        diff=diff or {},
        ip=client_ip(request) if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:300] if request else "",
    )
