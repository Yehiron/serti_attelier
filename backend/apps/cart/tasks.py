from celery import shared_task

from .services import delete_expired_carts


@shared_task(name="apps.cart.tasks.delete_expired_carts")  # type: ignore[untyped-decorator]
def cleanup_carts() -> int:
    return delete_expired_carts()
