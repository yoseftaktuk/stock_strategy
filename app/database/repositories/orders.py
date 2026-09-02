from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.exceptions import EntityNotFoundError
from app.database.mappers import order as order_mapper
from app.database.models import OrderModel
from app.domain.enums import OrderStatus, TradingMode
from app.domain.models.order import Order

OPEN_STATUSES = {
    OrderStatus.CREATED.value,
    OrderStatus.VALIDATED.value,
    OrderStatus.SUBMITTED.value,
    OrderStatus.ACKNOWLEDGED.value,
    OrderStatus.PARTIALLY_FILLED.value,
}


class PostgresOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, order: Order, mode: TradingMode) -> Order:
        model = order_mapper.from_domain(order, mode=mode)
        self._session.add(model)
        self._session.flush()
        return order_mapper.to_domain(model)

    def get_by_id(self, order_id: int) -> Order:
        model = self._session.get(OrderModel, order_id)
        if model is None:
            raise EntityNotFoundError(f"Order with id {order_id} not found")
        return order_mapper.to_domain(model)

    def get_by_client_order_id(self, client_order_id: str) -> Order:
        model = self._session.scalar(
            select(OrderModel).where(OrderModel.client_order_id == client_order_id)
        )
        if model is None:
            raise EntityNotFoundError(f"Order with client_order_id {client_order_id} not found")
        return order_mapper.to_domain(model)

    def get_open_orders(self) -> Sequence[Order]:
        models = self._session.scalars(
            select(OrderModel).where(OrderModel.status.in_(OPEN_STATUSES))
        ).all()
        return [order_mapper.to_domain(model) for model in models]

    def update_status(self, client_order_id: str, status: OrderStatus) -> Order:
        model = self._session.scalar(
            select(OrderModel).where(OrderModel.client_order_id == client_order_id)
        )
        if model is None:
            raise EntityNotFoundError(f"Order with client_order_id {client_order_id} not found")
        model.status = status.value
        self._session.flush()
        return order_mapper.to_domain(model)
