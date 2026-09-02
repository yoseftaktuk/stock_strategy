from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    quantity: Decimal
    price: Decimal
    commission: Decimal
    timestamp: datetime
    slippage: Decimal = Decimal("0")
    cash: Decimal | None = None
    position_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise DomainValidationError("order_id must not be empty")
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be greater than zero")
        if self.price < 0:
            raise DomainValidationError("price must be non-negative")
        if self.commission < 0:
            raise DomainValidationError("commission must be non-negative")
        if self.slippage < 0:
            raise DomainValidationError("slippage must be non-negative")
        if self.cash is not None and self.cash < 0:
            raise DomainValidationError("cash must be non-negative")
        if self.position_quantity is not None and self.position_quantity < 0:
            raise DomainValidationError("position_quantity must be non-negative")
        if self.timestamp.tzinfo is None or self.timestamp.tzinfo.utcoffset(self.timestamp) is None:
            raise DomainValidationError("timestamp must be timezone-aware")
