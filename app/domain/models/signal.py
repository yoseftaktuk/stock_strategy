from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class MomentumSignal:
    symbol: str
    date: date
    momentum: Decimal
    rank: int
    eligible: bool

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.rank < 0:
            raise DomainValidationError("rank must be non-negative")
