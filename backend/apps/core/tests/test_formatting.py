from datetime import UTC, datetime

import pytest

from apps.core.formatting import format_bogota_datetime, format_cop


@pytest.mark.parametrize(
    ("cents", "locale", "expected"),
    [
        (400_000_000, "es", "$ 4.000.000"),
        (400_000_000, "en", "COP 4,000,000"),
        (123_456, "es", "$ 1.234,56"),
        (123_456, "en", "COP 1,234.56"),
        (0, "es", "$ 0"),
    ],
)
def test_format_cop(cents: int, locale: str, expected: str) -> None:
    assert format_cop(cents, locale) == expected


def test_format_bogota_datetime_converts_from_utc() -> None:
    moment = datetime(2026, 10, 25, 19, 23, tzinfo=UTC)  # 14:23 in Bogotá (UTC-5)
    expected_es = "25 de octubre de 2026, 2:23 p. m. (hora de Colombia)"
    assert format_bogota_datetime(moment, "es") == expected_es
    assert format_bogota_datetime(moment, "en") == "October 25, 2026, 2:23 PM (Colombia time)"


def test_format_bogota_datetime_midnight_and_morning() -> None:
    assert format_bogota_datetime(datetime(2026, 1, 1, 5, 5, tzinfo=UTC), "es").startswith(
        "1 de enero de 2026, 12:05 a. m."
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MEDELLÍN", "Medellín"),
        ("BOGOTÁ, D.C.", "Bogotá, D.C."),
        ("SAN ANDRÉS DE TUMACO", "San Andrés de Tumaco"),
        (
            "ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA",
            "Archipiélago de San Andrés, Providencia y Santa Catalina",
        ),
        ("EL CARMEN DE VIBORAL", "El Carmen de Viboral"),
        ("NORTE DE SANTANDER", "Norte de Santander"),
    ],
)
def test_place_name(raw: str, expected: str) -> None:
    from apps.core.formatting import place_name

    assert place_name(raw) == expected
