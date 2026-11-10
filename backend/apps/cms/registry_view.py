from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .documents import require_capability
from .registry import export_registry


@require_GET
def section_registry(request):
    require_capability(request.user, "edit")
    response = JsonResponse(export_registry(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "private, no-store"
    return response
