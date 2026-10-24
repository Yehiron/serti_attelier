from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns: list[URLPattern | URLResolver] = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
]

if settings.API_SCHEMA_PUBLIC:
    urlpatterns.append(path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"))
