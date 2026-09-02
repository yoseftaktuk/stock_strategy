from decimal import Decimal

from app.domain.enums import OrderSide, OrderType
from app.domain.models.order import Order

SAMPLE_MARKET_ORDER = Order(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=Decimal("10"),
    order_type=OrderType.MARKET,
    limit_price=None,
    client_order_id="order-001",
)

SAMPLE_LIMIT_ORDER = Order(
    symbol="AAPL",
    side=OrderSide.SELL,
    quantity=Decimal("5"),
    order_type=OrderType.LIMIT,
    limit_price=Decimal("160.00"),
    client_order_id="order-002",
)
