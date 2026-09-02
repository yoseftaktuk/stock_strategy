from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class EquityPoint:
    date: date
    equity: Decimal
    cash: Decimal
    returns: Decimal
    drawdown: Decimal

    def __post_init__(self) -> None:
        if self.equity < 0:
            raise DomainValidationError("equity must be non-negative")
        if self.cash < 0:
            raise DomainValidationError("cash must be non-negative")
