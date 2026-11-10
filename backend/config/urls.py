from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView

from apps.cms.editor import action
from apps.cms.editor_api import document as editor_document
from apps.cms.editor_api import editor
from apps.cms.editor_api import photo as editor_photo
from apps.cms.history import history
from apps.cms.publishing import review_publish
from apps.cms.registry_view import section_registry
from apps.notifications import views as notification_views

urlpatterns: list[URLPattern | URLResolver] = [
    path(
        settings.ADMIN_URL + "notifications/unread/",
        notification_views.unread,
        name="admin-notifications-unread",
    ),
    path(
        settings.ADMIN_URL + "notifications/read/",
        notification_views.mark_read,
        name="admin-notifications-read",
    ),
    path(
        settings.ADMIN_URL + "notifications/", notification_views.page, name="admin-notifications"
    ),
    path(settings.ADMIN_URL, include("apps.accounts.urls")),
    path(settings.ADMIN_URL + "editor/foto/", editor_photo, name="cms-editor-photo"),
    path(settings.ADMIN_URL + "editor/documento/", editor_document, name="cms-editor-document"),
    path(settings.ADMIN_URL + "editor/", admin.site.admin_view(editor), name="visual-editor"),
    path(
        settings.ADMIN_URL + "editor/<slug:action>/",
        admin.site.admin_view(action),
        name="visual-editor-action",
    ),
    path(
        settings.ADMIN_URL + "revisar-publicacion/<str:key>/",
        admin.site.admin_view(review_publish),
        name="cms-review-publish",
    ),
    path(settings.ADMIN_URL + "publicaciones/", admin.site.admin_view(history), name="cms-history"),
    path(
        settings.ADMIN_URL + "section-registry/",
        admin.site.admin_view(section_registry),
        name="cms-section-registry",
    ),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/", include("apps.payments.urls")),
    path("api/v1/", include("apps.orders.urls")),
    path("api/v1/", include("apps.cms.api.urls")),
    path("api/v1/catalog/", include("apps.catalog.api.urls")),
    path("api/v1/", include("apps.core.urls")),
]

if settings.API_SCHEMA_PUBLIC:
    urlpatterns.append(path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"))

if settings.DEBUG:
    # Development only: production serves uploaded media straight from Caddy (Phase 9).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
