from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import OrderModel
from app.database.repositories.fills import PostgresFillRepository
from app.database.repositories.orders import PostgresOrderRepository
from app.domain.enums import TradingMode
from app.domain.models.fill import Fill
from tests.fixtures.orders import SAMPLE_MARKET_ORDER


@pytest.mark.integration
def test_fill_repository_save_and_get(db_session: Session) -> None:
    order_repository = PostgresOrderRepository(db_session)
    fill_repository = PostgresFillRepository(db_session)

    order_repository.save(SAMPLE_MARKET_ORDER, mode=TradingMode.BACKTEST)
    db_session.flush()

    order_db_id = db_session.scalar(
        select(OrderModel.id).where(OrderModel.client_order_id == "order-001")
    )
    assert order_db_id is not None

    fill = Fill(
        order_id="order-001",
        symbol="AAPL",
        quantity=Decimal("10"),
        price=Decimal("154.00"),
        commission=Decimal("1.00"),
        timestamp=datetime(2024, 1, 2, 16, 5, tzinfo=timezone.utc),
    )
    saved = fill_repository.save(fill, order_db_id=order_db_id)
    db_session.commit()

    fills = fill_repository.get_by_order_id(order_db_id)
    assert len(fills) == 1
    assert saved.price == Decimal("154.00")
