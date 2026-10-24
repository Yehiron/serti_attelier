from collections.abc import Callable
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from .selectors import pending_second_factor


class AdminAccessMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        prefix = "/" + settings.ADMIN_URL
        relative = request.path.removeprefix(prefix)
        exempt = relative in {
            "login/",
            "logout/",
            "2fa/setup/",
            "2fa/verify/",
        } or relative.startswith("password-reset/")
        user = request.user
        # Middleware covers all Unfold/admin URLs, including third-party model admins,
        # without replacing Unfold's AdminSite or wrapping individual model views.
        if (
            request.path.startswith(prefix)
            and not request.path.startswith(settings.STATIC_URL)
            and not exempt
            and user.is_authenticated
            and user.is_staff
        ):
            target = pending_second_factor(user)
            if target:
                return redirect(
                    prefix + f"2fa/{target}/?" + urlencode({"next": request.get_full_path()})
                )
        return self.get_response(request)
