from celery import shared_task

from .services import deliver, retry_due


@shared_task  # type: ignore[untyped-decorator]
def send_delivery(delivery_id: int) -> None:
    deliver(delivery_id)


@shared_task  # type: ignore[untyped-decorator]
def retry_failed() -> int:
    return retry_due()
