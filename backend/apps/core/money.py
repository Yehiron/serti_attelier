"""Money in integer COP cents (ADR-006).

Floats are rejected on purpose: every amount that reaches Wompi is an integer
number of cents, and rounding must never happen implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

COP = "COP"


class CurrencyMismatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    amount_cents: int
    currency: str = COP

    def __post_init__(self) -> None:
        if isinstance(self.amount_cents, bool) or not isinstance(self.amount_cents, int):
            raise TypeError("amount_cents must be an int")
        if self.currency != COP:
            raise ValueError(f"Unsupported currency: {self.currency}")

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @classmethod
    def from_pesos(cls, pesos: int) -> Money:
        if isinstance(pesos, bool) or not isinstance(pesos, int):
            raise TypeError("pesos must be an int")
        return cls(pesos * 100)

    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("Can only combine Money with Money")
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"{self.currency} != {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_cents + other.amount_cents, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_cents - other.amount_cents, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_cents < other.amount_cents

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_cents <= other.amount_cents

    def percentage(self, percent: int) -> Money:
        """Return ``percent``% of this amount, rounded down to a whole cent."""
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError("percent must be an int between 0 and 100")
        return Money(self.amount_cents * percent // 100, self.currency)

    def as_dict(self) -> dict[str, int | str]:
        return {"amount_cents": self.amount_cents, "currency": self.currency}
