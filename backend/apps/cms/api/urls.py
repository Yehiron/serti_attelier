from django.urls import path

from .views import HomeView, PageView, PersonalizationView, PreviewVerifyView, SiteSettingsView

urlpatterns = [
    path("cms/home", HomeView.as_view(), name="cms-home"),
    path("cms/pages/kind/<str:kind>", PageView.as_view(), name="cms-page-kind"),
    path("cms/pages/<slug:slug>", PageView.as_view(), name="cms-page"),
    path("cms/personalization", PersonalizationView.as_view(), name="cms-personalization"),
    path("cms/preview/verify", PreviewVerifyView.as_view(), name="cms-preview-verify"),
    path("site/settings", SiteSettingsView.as_view(), name="site-settings"),
]
