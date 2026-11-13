from celery import shared_task


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def render_media(self, asset_id, version):
    from .media import render
    from .models import MediaAsset

    try:
        render(asset_id, version)
    except Exception as exc:
        MediaAsset.objects.filter(pk=asset_id, version=version).update(state="failed")
        raise self.retry(exc=exc) from exc


@shared_task
def cleanup_media():
    """Opt-in: intentionally absent from the default beat schedule."""
    from django.conf import settings

    from .management.commands.cleanup_cms_media import collect

    if getattr(settings, "CMS_MEDIA_WEEKLY_CLEANUP", False):
        return len(collect(execute=True))
    return 0


@shared_task(bind=True, max_retries=5)
def revalidate_tags(self, tags, *, invalidation_id=None):
    """Duplicate delivery is harmless: expiring a cache tag is idempotent."""
    import json
    import logging
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    from django.conf import settings
    from django.utils import timezone

    from .models import CacheInvalidation

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    from urllib.parse import urlsplit

    from django.db import transaction

    # Serialize duplicate deliveries, including the bounded HTTP call. Catch failures
    # inside the transaction so their audit state commits before Celery retries.
    retry = False
    with transaction.atomic():
        row = CacheInvalidation.objects.select_for_update().filter(pk=invalidation_id).first()
        if invalidation_id is not None and row is None:
            return
        if row and row.state in {"sent", "failed"}:
            return
        attempts = (row.attempts if row else self.request.retries) + 1
        try:
            url = settings.FRONTEND_INTERNAL_URL.rstrip("/") + "/api/internal/revalidate"
            parsed = urlsplit(url)
            if (
                not settings.REVALIDATE_SECRET
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Invalidación no configurada")
            req = Request(  # noqa: S310 — only configured HTTP(S), no redirects
                url,
                data=json.dumps({"tags": sorted(set(tags))}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Revalidate-Secret": settings.REVALIDATE_SECRET,
                },
                method="POST",
            )
            with build_opener(NoRedirect).open(req, timeout=5) as response:
                if response.status != 200 or json.loads(response.read(1024)).get("ok") is not True:
                    raise ValueError("Respuesta inválida")
            state = "sent"
        except Exception:
            state = "failed" if attempts >= 6 else "pending"
            retry = state == "pending"
            logging.getLogger(__name__).warning(
                "Actualización CMS %s (registro %s, intento %s).",
                "fallida" if state == "failed" else "pendiente",
                invalidation_id,
                attempts,
            )
        if row:
            CacheInvalidation.objects.filter(pk=row.pk).update(
                state=state, attempts=attempts, updated_at=timezone.now()
            )
    if retry:
        # Sanitized exception only: Celery logs retry exceptions.
        raise self.retry(
            exc=RuntimeError("Actualización CMS pendiente"),
            countdown=min(30 * 2 ** (attempts - 1), 600),
        ) from None


@shared_task
def retry_pending_revalidations():
    """Recover broker failures and interrupted workers without retrying exhausted rows."""
    from datetime import timedelta

    from django.utils import timezone

    from .invalidation import dispatch
    from .models import CacheInvalidation

    ids = CacheInvalidation.objects.filter(
        state="pending", updated_at__lt=timezone.now() - timedelta(minutes=15)
    ).values_list("pk", flat=True)[:100]
    for pk in ids:
        dispatch(pk)
