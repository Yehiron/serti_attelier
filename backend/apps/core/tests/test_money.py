import pytest

from apps.core.money import CurrencyMismatchError, Money


def test_from_pesos_converts_to_cents() -> None:
    assert Money.from_pesos(4_800_000).amount_cents == 480_000_000


@pytest.mark.parametrize("value", [10.5, "100", True, None])
def test_rejects_non_integer_amounts(value: object) -> None:
    with pytest.raises(TypeError):
        Money(value)  # type: ignore[arg-type]


def test_rejects_other_currencies() -> None:
    with pytest.raises(ValueError):
        Money(100, "USD")


def test_arithmetic_and_comparison() -> None:
    a, b = Money(1_000), Money(250)
    assert a + b == Money(1_250)
    assert a - b == Money(750)
    assert b < a
    assert a <= Money(1_000)


def test_cannot_mix_with_non_money() -> None:
    with pytest.raises(TypeError):
        Money(100) + 5  # type: ignore[operator]


def test_currency_mismatch_error_is_value_error() -> None:
    assert issubclass(CurrencyMismatchError, ValueError)


@pytest.mark.parametrize(
    ("amount", "percent", "expected"),
    [(10_000, 10, 1_000), (999, 10, 99), (12_345, 0, 0), (12_345, 100, 12_345)],
)
def test_percentage_rounds_down(amount: int, percent: int, expected: int) -> None:
    assert Money(amount).percentage(percent) == Money(expected)


@pytest.mark.parametrize("percent", [-1, 101, 12.5])
def test_percentage_rejects_invalid_values(percent: object) -> None:
    with pytest.raises(ValueError):
        Money(100).percentage(percent)  # type: ignore[arg-type]


def test_as_dict() -> None:
    assert Money(500).as_dict() == {"amount_cents": 500, "currency": "COP"}
