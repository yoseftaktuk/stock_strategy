from decimal import Decimal

import pytest

from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.models.order import Order


@pytest.mark.unit
def test_order_dataclass_defaults() -> None:
    order = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.LIMIT,
        limit_price=Decimal("150.00"),
        client_order_id="order-001",
    )
    assert order.status == OrderStatus.CREATED
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.LIMIT
