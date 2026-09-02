from dataclasses import dataclass
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    valued: bool = True

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.quantity < 0:
            raise DomainValidationError("quantity must be non-negative")
        if self.average_price < 0:
            raise DomainValidationError("average_price must be non-negative")
        if self.market_price < 0:
            raise DomainValidationError("market_price must be non-negative")

    @property
    def market_value(self) -> Decimal:
        if not self.valued:
            return Decimal("0")
        return self.market_price * self.quantity
