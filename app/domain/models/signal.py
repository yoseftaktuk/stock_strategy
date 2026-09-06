from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityCarrier, IdentityRef, require_matching_ticker


@dataclass(frozen=True)
class MomentumSignal(IdentityCarrier):
    symbol: str
    date: date
    momentum: Decimal
    rank: int
    eligible: bool
    identity: IdentityRef | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.rank < 0:
            raise DomainValidationError("rank must be non-negative")
        require_matching_ticker(self.symbol, self.identity)
