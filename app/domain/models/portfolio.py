from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.exceptions import DomainValidationError
from app.domain.models.position import Position


@dataclass(frozen=True)
class Portfolio:
    cash: Decimal
    positions: tuple[Position, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.cash < 0:
            raise DomainValidationError("cash must be non-negative")
        if not isinstance(self.positions, tuple):
            object.__setattr__(self, "positions", tuple(self.positions))

    @property
    def equity(self) -> Decimal:
        positions_value = sum(
            (position.market_value for position in self.positions),
            start=Decimal("0"),
        )
        return self.cash + positions_value
