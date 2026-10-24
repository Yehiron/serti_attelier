from celery import shared_task

from . import services


@shared_task(name="apps.inventory.tasks.release_expired_reservations")  # type: ignore[untyped-decorator]  # Celery has no stubs.
def release_expired_reservations() -> int:
    return services.release_expired_reservations()
