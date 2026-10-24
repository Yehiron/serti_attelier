from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import AuditedPasswordResetForm

urlpatterns = [
    path(
        "password_change/",
        admin.site.admin_view(views.AuditedPasswordChangeView.as_view()),
        name="admin-password-change",
    ),
    path("2fa/setup/", views.setup, name="admin-2fa-setup"),
    path("2fa/verify/", views.verify, name="admin-2fa-verify"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=AuditedPasswordResetForm,
            success_url=reverse_lazy("password_reset_done"),
            email_template_name="registration/password_reset_email.html",
        ),
        name="admin_password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        views.AuditedPasswordResetConfirmView.as_view(
            success_url=reverse_lazy("password_reset_complete")
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
