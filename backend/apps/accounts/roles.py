from django.contrib.auth.models import AnonymousUser

from .models import User

PROPIETARIO = "Propietario"
OPERACIONES = "Operaciones"
CONTENIDO = "Contenido"
ROLE_PERMISSIONS = {
    PROPIETARIO: {
        *(f"accounts.{action}_user" for action in ("add", "change", "delete", "view")),
        *(f"auth.{action}_group" for action in ("add", "change", "delete", "view")),
        "audit.view_auditlog",
        "otp_totp.view_totpdevice",
        "otp_totp.delete_totpdevice",
    },
    OPERACIONES: set(),
    CONTENIDO: set(),
}


def has_role(user: User | AnonymousUser, role: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=role).exists()


CATALOG_MODELS = (
    "piece",
    "pieceimage",
    "category",
    "collection",
    "stone",
    "material",
    "collectionpiece",
    "piecerelation",
)
for role in (PROPIETARIO, OPERACIONES, CONTENIDO):
    actions = (
        ("add", "change", "delete", "view") if role != CONTENIDO else ("add", "change", "view")
    )
    ROLE_PERMISSIONS[role].update(
        f"catalog.{action}_{model}" for model in CATALOG_MODELS for action in actions
    )
    ROLE_PERMISSIONS[role].update({"core.view_department", "core.view_municipality"})
for role in (PROPIETARIO, OPERACIONES):
    ROLE_PERMISSIONS[role].update(
        {
            "catalog.change_piece_price",
            "inventory.view_piecereservation",
            "inventory.view_piecestatuschange",
        }
    )
ROLE_PERMISSIONS[PROPIETARIO].update({"core.view_sitesettings", "core.change_sitesettings"})


for role in (PROPIETARIO, CONTENIDO, OPERACIONES):
    cms_actions = ("view",) if role == OPERACIONES else ("add", "change", "view")
    ROLE_PERMISSIONS[role].update(
        f"cms.{action}_{model}"
        for model in ("homesection", "page", "personalizationservice")
        for action in cms_actions
    )
    ROLE_PERMISSIONS[role].update({"cms.view_homepublication", "cms.view_pagerevision"})
    if role != OPERACIONES:
        ROLE_PERMISSIONS[role].add("cms.publish_content")

for role in (PROPIETARIO, OPERACIONES):
    ROLE_PERMISSIONS[role].update(
        {"orders.view_order", "orders.change_order", "orders.change_fulfillment"}
    )
    ROLE_PERMISSIONS[role].update(
        f"promotions.{action}_coupon" for action in ("add", "change", "view", "delete")
    )

for role in (PROPIETARIO, OPERACIONES):
    ROLE_PERMISSIONS[role].update(
        {
            "payments.view_paymentattempt",
            "payments.view_paymentevent",
            "payments.confirm_manual_payment",
        }
    )

for role in (PROPIETARIO, OPERACIONES):
    ROLE_PERMISSIONS[role].update(
        {"notifications.view_notificationdelivery", "notifications.resend_notificationdelivery"}
    )

for role in (PROPIETARIO, OPERACIONES):
    ROLE_PERMISSIONS[role].update(
        {"orders.export_orders", "orders.add_ordernote", "orders.view_ordernote"}
    )
