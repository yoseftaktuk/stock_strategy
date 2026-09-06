from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityCarrier, IdentityRef, require_matching_ticker

_WEIGHT_TOLERANCE = Decimal("0.0000001")


@dataclass(frozen=True)
class TargetPosition(IdentityCarrier):
    symbol: str
    target_weight: Decimal
    identity: IdentityRef | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.target_weight < 0:
            raise DomainValidationError("target_weight must be non-negative")
        require_matching_ticker(self.symbol, self.identity)


@dataclass(frozen=True)
class TargetPortfolio:
    positions: tuple[TargetPosition, ...] = field(default_factory=tuple)
    cash_weight: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if not isinstance(self.positions, tuple):
            object.__setattr__(self, "positions", tuple(self.positions))
        if self.cash_weight < 0:
            raise DomainValidationError("cash_weight must be non-negative")
        invested = sum((item.target_weight for item in self.positions), Decimal("0"))
        total = invested + self.cash_weight
        if abs(total - Decimal("1")) > _WEIGHT_TOLERANCE:
            raise DomainValidationError(
                f"target weights plus cash_weight must sum to 1, got {total}"
            )

    def weight_for(self, symbol: str) -> Decimal:
        """Return target weight for an execution ticker.

        Listing/display lookup only. Not a position identity key. Recycled
        tickers would collide here; OrderService nets by ``position_key``.
        """
        for item in self.positions:
            if item.symbol == symbol:
                return item.target_weight
        return Decimal("0")
