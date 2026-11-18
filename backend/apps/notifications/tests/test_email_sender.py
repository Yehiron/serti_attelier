from io import StringIO
from types import SimpleNamespace

import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from apps.notifications.email_checks import sender_errors


def config(**overrides):
    base = {
        "EMAIL_HOST": "smtp.resend.com",
        "EMAIL_USE_TLS": True,
        "EMAIL_USE_SSL": False,
        "EMAIL_HOST_USER": "resend",
        "EMAIL_HOST_PASSWORD": "re_test",
        "DEFAULT_FROM_EMAIL": "SERTI <pedidos@serti.co>",
        "PUBLIC_SITE_URL": "https://www.serti.co",
    }
    return SimpleNamespace(**(base | overrides))


def test_valid_sender_on_shop_domain_or_subdomain():
    assert sender_errors(config()) == []
    assert sender_errors(config(DEFAULT_FROM_EMAIL="pedidos@envios.serti.co")) == []


def test_unset_smtp_is_not_a_sender_error():
    assert sender_errors(config(EMAIL_HOST="")) == []


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"DEFAULT_FROM_EMAIL": "SERTI <no-reply@serti.localhost>"}, "de ejemplo"),
        ({"DEFAULT_FROM_EMAIL": "serti.joyas@gmail.com"}, "dominio de la tienda"),
        ({"DEFAULT_FROM_EMAIL": "pedidos@notserti.co"}, "dominio de la tienda"),
        ({"EMAIL_USE_TLS": False}, "TLS"),
        ({"EMAIL_HOST_PASSWORD": ""}, "credenciales"),
    ],
)
def test_sender_problems(overrides, fragment):
    assert any(fragment in error for error in sender_errors(config(**overrides)))


@pytest.mark.django_db
def test_send_test_email_uses_fictitious_content():
    out = StringIO()
    call_command("send_test_email", "check@example.com", stdout=out)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["check@example.com"] and "SRT-000000" in message.body
    assert message.alternatives and "Message-ID" in out.getvalue()


@pytest.mark.django_db
def test_send_test_email_rejects_invalid_recipient():
    with pytest.raises(CommandError):
        call_command("send_test_email", "no-es-un-correo")
