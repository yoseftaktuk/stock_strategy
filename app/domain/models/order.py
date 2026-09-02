from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Decimal | None
    client_order_id: str
    status: OrderStatus = field(default=OrderStatus.CREATED)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be greater than zero")
        if not self.client_order_id.strip():
            raise DomainValidationError("client_order_id must not be empty")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise DomainValidationError("limit orders require limit_price")
        if self.order_type == OrderType.LIMIT and self.limit_price is not None and self.limit_price <= 0:
            raise DomainValidationError("limit_price must be greater than zero")
        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise DomainValidationError("market orders must not include limit_price")
