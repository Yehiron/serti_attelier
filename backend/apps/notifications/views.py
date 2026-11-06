from django.contrib import admin
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .panel import serialize_receipt, unread_data, visible_receipts


@never_cache
def unread(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    raw = request.GET.get("since", "0")
    if not raw.isdecimal() or len(raw) > 18:
        return JsonResponse({"error": "Identificador inválido."}, status=400)
    data = unread_data(request.user, int(raw))
    if data is None:
        return HttpResponseForbidden()
    return JsonResponse(data)


@never_cache
@csrf_protect
def mark_read(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    rows = visible_receipts(request.user)
    if rows is None:
        return HttpResponseForbidden()
    # Only the notices displayed before this high-water mark are acknowledged.
    raw = request.POST.get("through", "")
    if not raw.isdecimal() or len(raw) > 18:
        return JsonResponse({"error": "Identificador inválido."}, status=400)
    rows.filter(notification_id__lte=int(raw), read_at__isnull=True).update(read_at=timezone.now())
    return JsonResponse({"ok": True})


@never_cache
def page(request):
    rows = visible_receipts(request.user)
    if rows is None:
        return HttpResponseForbidden()
    page = Paginator(
        rows.select_related("notification__order").order_by("-notification_id"), 20
    ).get_page(request.GET.get("p"))
    return TemplateResponse(
        request,
        "admin/notifications/page.html",
        {
            **admin.site.each_context(request),
            "title": "Avisos de pedidos",
            "page": page,
            "notices": [serialize_receipt(row) for row in page],
        },
    )
