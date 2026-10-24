from typing import Any

from axes.signals import user_locked_out
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

from apps.accounts.models import User

from .services import record


@receiver(user_logged_in)
def logged_in(sender: object, request: HttpRequest, user: User, **kwargs: Any) -> None:
    record("auth.login", actor=user, request=request)


@receiver(user_logged_out)
def logged_out(sender: object, request: HttpRequest, user: User | None, **kwargs: Any) -> None:
    record("auth.logout", actor=user, request=request)


@receiver(user_login_failed)
def login_failed(
    sender: object, credentials: dict[str, object], request: HttpRequest | None, **kwargs: Any
) -> None:
    record(
        "auth.login_failed", diff={"username": [None, credentials.get("username")]}, request=request
    )


@receiver(user_locked_out)
def locked_out(sender: object, request: HttpRequest, **kwargs: Any) -> None:
    record("auth.locked_out", request=request)
