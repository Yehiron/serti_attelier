def order_paid(order_id: int) -> None:
    """Post-commit hook. Phase 7 will enqueue idempotent notifications here."""
