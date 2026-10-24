from ipaddress import ip_address

from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str | None:
    # Caddy appends the peer address: trust only the rightmost forwarded hop.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    value = forwarded.split(",")[-1].strip() if forwarded else request.META.get("REMOTE_ADDR")
    try:
        return str(ip_address(value)) if value else None
    except ValueError:
        return None
