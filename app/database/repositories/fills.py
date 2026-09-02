from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.mappers import fill as fill_mapper
from app.database.models import FillModel, OrderModel
from app.domain.models.fill import Fill


class PostgresFillRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, fill: Fill, order_db_id: int) -> Fill:
        model = fill_mapper.from_domain(fill, order_db_id=order_db_id)
        self._session.add(model)
        self._session.flush()
        order = self._session.get(OrderModel, order_db_id)
        client_order_id = order.client_order_id if order is not None else fill.order_id
        return fill_mapper.to_domain(model, order_client_id=client_order_id)

    def get_by_order_id(self, order_db_id: int) -> Sequence[Fill]:
        order = self._session.get(OrderModel, order_db_id)
        client_order_id = order.client_order_id if order is not None else ""
        models = self._session.scalars(
            select(FillModel).where(FillModel.order_id == order_db_id)
        ).all()
        return [fill_mapper.to_domain(model, order_client_id=client_order_id) for model in models]
