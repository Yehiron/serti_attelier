PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"approved", "declined", "error", "expired"}),
    "awaiting_manual_payment": frozenset({"approved", "expired"}),
    "declined": frozenset({"pending", "approved"}),
    "error": frozenset({"pending", "approved"}),
    "approved": frozenset({"voided"}),
    "expired": frozenset({"approved"}),
    "voided": frozenset(),
}
FULFILLMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "unfulfilled": frozenset({"preparing", "cancelled"}),
    "preparing": frozenset({"shipped", "cancelled"}),
    "shipped": frozenset({"delivered", "returned"}),
    "delivered": frozenset({"returned"}),
    "cancelled": frozenset(),
    "returned": frozenset(),
}
