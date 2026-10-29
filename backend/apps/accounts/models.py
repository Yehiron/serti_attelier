from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    email = models.EmailField(_("correo electrónico"), unique=True)
    password = models.CharField(_("Contraseña"), max_length=128)
    last_login = models.DateTimeField(_("Último inicio de sesión"), blank=True, null=True)
    is_superuser = models.BooleanField(
        _("Superusuario"),
        default=False,
        help_text=_(
            "Designates that this user has all permissions without explicitly assigning them."
        ),
    )
    username = models.CharField(
        _("Nombre de usuario"),
        max_length=150,
        unique=True,
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[UnicodeUsernameValidator()],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_("Nombre"), max_length=150, blank=True)
    last_name = models.CharField(_("Apellidos"), max_length=150, blank=True)
    is_staff = models.BooleanField(
        _("Acceso a administración"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("Activo"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(_("Fecha de registro"), default=timezone.now)
    groups = models.ManyToManyField(  # type: ignore[assignment]  # Concrete through model.
        "auth.Group",
        verbose_name=_("Grupos"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="user_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(  # type: ignore[assignment]  # Concrete through model.
        "auth.Permission",
        verbose_name=_("Permisos de usuario"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_set",
        related_query_name="user",
    )
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
