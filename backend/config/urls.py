from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns: list[URLPattern | URLResolver] = [
    path(settings.ADMIN_URL, include("apps.accounts.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include("apps.cms.api.urls")),
    path("api/v1/catalog/", include("apps.catalog.api.urls")),
    path("api/v1/", include("apps.core.urls")),
]

if settings.API_SCHEMA_PUBLIC:
    urlpatterns.append(path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"))

if settings.DEBUG:
    # Development only: production serves uploaded media straight from Caddy (Phase 9).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
