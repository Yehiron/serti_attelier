import contextlib
from collections import defaultdict
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin

from .models import AuditLog
from .presentation import ACTION_LABELS, ACTIONS, MODULES, changes, describe, who

BOGOTA = ZoneInfo("America/Bogota")
# Automated tests: e2e users, objects named «E2E …» / «… prueba …», and system entries about
# orders or payment attempts that no longer exist (the e2e cleanup is the only thing that
# deletes those; real orders are never deleted).
TEST_QUERY = (
    Q(actor_repr__istartswith="e2e-")
    | Q(actor_repr__iregex=r"(^|[^a-z0-9])e2e([^a-z0-9]|$)")
    | Q(object_repr__iregex=r"(^|[^a-z0-9])(e2e|prueba)([^a-z0-9]|$)")
)


def automated_test_query() -> Q:
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import CharField
    from django.db.models.functions import Cast

    from apps.orders.models import Order
    from apps.payments.models import PaymentAttempt

    query = TEST_QUERY
    for model in (Order, PaymentAttempt):
        existing = model.objects.annotate(key=Cast("pk", CharField())).values("key")
        query |= Q(actor__isnull=True, content_type=ContentType.objects.get_for_model(model)) & ~Q(
            object_id__in=existing
        )
    return query


FILTERS = ("modulo", "periodo", "persona", "seguridad", "pruebas")


def rows_for(entries):
    entries = list(entries)
    targets = defaultdict(list)
    for entry in entries:
        if entry.content_type_id and entry.object_id:
            targets[entry.content_type].append(entry.object_id)
    existing = {}
    for content_type, ids in targets.items():
        model = content_type.model_class()
        if not model:
            continue
        # Invalid or stale primary keys should never break the audit screen.
        valid = []
        for pk in ids:
            try:
                valid.append(model._meta.pk.to_python(pk))
            except (ValueError, TypeError, OverflowError, ValidationError):
                continue
        existing[content_type.pk] = {
            str(pk) for pk in model._base_manager.filter(pk__in=valid).values_list("pk", flat=True)
        }
    rows = []
    for entry in entries:
        action = ACTIONS.get(entry.action, {"module": "Otros", "icon": "•"})
        name = who(entry)
        url = None
        deleted = False
        if entry.content_type_id and entry.object_id:
            deleted = entry.object_id not in existing.get(entry.content_type_id, set())
            if not deleted:
                with contextlib.suppress(NoReverseMatch):
                    url = reverse(
                        f"admin:{entry.content_type.app_label}_{entry.content_type.model}_change",
                        args=[entry.object_id],
                    )
        rows.append(
            {
                "entry": entry,
                "description": describe(entry),
                "who": name,
                "initials": "".join(word[0] for word in name.split()[:2]).upper(),
                "module": action["module"],
                "icon": action["icon"],
                "unknown": entry.action not in ACTIONS,
                "changes": changes(entry),
                "date": timezone.localtime(entry.at, BOGOTA),
                "url": url,
                "deleted": deleted,
                "security": entry.action.startswith("auth.")
                or entry.action == "accounts.access_changed",
            }
        )
    return rows


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):  # type: ignore[misc]  # Unfold has no stubs.
    change_list_template = "admin/audit/auditlog/change_list.html"
    change_form_template = "admin/audit/auditlog/change_form.html"
    list_display = ("at", "actor_repr", "action_label", "object_repr")
    search_fields = ("actor_repr", "object_repr", "action", "object_id")
    list_per_page = 50
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    @admin.display(description="Acción", ordering="action")
    def action_label(self, obj):
        return ACTION_LABELS.get(obj.action, "Acción registrada")

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("actor", "content_type")
        if not hasattr(request, "audit_filters"):
            return qs
        filters = request.audit_filters
        if filters.get("pruebas") != "mostrar":
            qs = qs.exclude(automated_test_query())
        module = filters.get("modulo")
        if module in MODULES:
            qs = qs.filter(
                action__in=[key for key, value in ACTIONS.items() if value["module"] == module]
            )
        period = filters.get("periodo")
        if period in {"hoy", "7", "30"}:
            today = timezone.localtime(timezone.now(), BOGOTA).date()
            start = today - timedelta(days={"hoy": 0, "7": 6, "30": 29}[period])
            from datetime import datetime, time

            qs = qs.filter(at__gte=datetime.combine(start, time.min, tzinfo=BOGOTA))
        person = filters.get("persona")
        if person == "sistema":
            qs = qs.filter(actor__isnull=True, actor_repr="")
        elif person:
            qs = qs.filter(actor_repr=person)
        if filters.get("seguridad") == "1":
            qs = qs.filter(Q(action__startswith="auth.") | Q(action="accounts.access_changed"))
        return qs

    def changelist_view(self, request, extra_context=None):
        original = request.GET
        request.audit_filters = {key: original.get(key, "") for key in FILTERS}
        cleaned = original.copy()
        for key in FILTERS:
            cleaned.pop(key, None)
        request.GET = cleaned
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original
        if not hasattr(response, "context_data") or "cl" not in response.context_data:
            return response
        cl = response.context_data["cl"]
        rows = rows_for(cl.result_list)
        today = timezone.localtime(timezone.now(), BOGOTA).date()
        groups: list[dict[str, Any]] = []
        for row in rows:
            day = row["date"].date()
            if not groups or groups[-1]["day"] != day:
                groups.append(
                    {
                        "day": day,
                        "label": "Hoy"
                        if day == today
                        else "Ayer"
                        if day == today - timedelta(days=1)
                        else None,
                        "rows": [],
                    }
                )
            groups[-1]["rows"].append(row)

        def url(**updates):
            query = original.copy()
            query.pop("p", None)
            for key, value in updates.items():
                if value:
                    query[key] = value
                else:
                    query.pop(key, None)
            return "?" + query.urlencode()

        selected = request.audit_filters
        people = (
            AuditLog.objects.exclude(actor_repr="")
            .exclude(automated_test_query())
            .order_by("actor_repr")
            .values_list("actor_repr", flat=True)
            .distinct()
        )
        page = cl.page_num
        response.context_data.update(
            {
                "aud_groups": groups,
                "aud_filters": selected,
                "aud_modules": [
                    {"label": item, "url": url(modulo=item), "active": selected["modulo"] == item}
                    for item in MODULES
                ],
                "aud_all_modules": url(modulo=""),
                "aud_periods": [
                    {
                        "label": label,
                        "url": url(periodo=value),
                        "active": selected["periodo"] == value,
                    }
                    for label, value in (
                        ("Todo", ""),
                        ("Hoy", "hoy"),
                        ("7 días", "7"),
                        ("30 días", "30"),
                    )
                ],
                "aud_people": people,
                "aud_hidden": AuditLog.objects.filter(automated_test_query()).count(),
                "aud_toggle_url": url(
                    pruebas="" if selected["pruebas"] == "mostrar" else "mostrar"
                ),
                "aud_security_url": url(seguridad="" if selected["seguridad"] == "1" else "1"),
                "aud_previous": url(p=str(page - 1)) if page > 1 else None,
                "aud_next": url(p=str(page + 1)) if page < cl.paginator.num_pages else None,
                "aud_page": page,
                "aud_pages": cl.paginator.num_pages,
            }
        )
        return response

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        context = dict(extra_context or {})
        if obj:
            context["aud_row"] = rows_for([obj])[0]
        return super().change_view(request, object_id, form_url, extra_context=context)

    def has_view_permission(self, request: HttpRequest, obj=None):
        return request.user.has_perm("audit.view_auditlog")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
