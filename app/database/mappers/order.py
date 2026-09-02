from app.database.models import OrderModel
from app.domain.enums import OrderSide, OrderStatus, OrderType, TradingMode
from app.domain.models.order import Order


def to_domain(model: OrderModel) -> Order:
    return Order(
        symbol=model.symbol,
        side=OrderSide(model.side),
        quantity=model.quantity,
        order_type=OrderType(model.order_type),
        limit_price=model.limit_price,
        client_order_id=model.client_order_id,
        status=OrderStatus(model.status),
    )


def from_domain(order: Order, *, mode: TradingMode) -> OrderModel:
    return OrderModel(
        client_order_id=order.client_order_id,
        broker_order_id=None,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        limit_price=order.limit_price,
        status=order.status.value,
        mode=mode.value,
    )
