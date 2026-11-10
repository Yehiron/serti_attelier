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
