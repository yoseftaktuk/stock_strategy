import pytest
from sqlalchemy.orm import Session

from app.database.exceptions import EntityNotFoundError
from app.database.repositories.orders import PostgresOrderRepository
from app.domain.enums import OrderStatus, TradingMode
from tests.fixtures.orders import SAMPLE_LIMIT_ORDER, SAMPLE_MARKET_ORDER


@pytest.mark.integration
def test_order_repository_save_and_get(db_session: Session) -> None:
    repository = PostgresOrderRepository(db_session)
    saved = repository.save(SAMPLE_MARKET_ORDER, mode=TradingMode.BACKTEST)
    db_session.commit()

    loaded = repository.get_by_client_order_id(saved.client_order_id)
    assert loaded.symbol == "AAPL"
    assert loaded.quantity == SAMPLE_MARKET_ORDER.quantity


@pytest.mark.integration
def test_order_repository_get_open_orders(db_session: Session) -> None:
    repository = PostgresOrderRepository(db_session)
    repository.save(SAMPLE_MARKET_ORDER, mode=TradingMode.BACKTEST)
    repository.save(SAMPLE_LIMIT_ORDER, mode=TradingMode.BACKTEST)
    db_session.commit()

    open_orders = repository.get_open_orders()
    assert len(open_orders) == 2


@pytest.mark.integration
def test_order_repository_update_status(db_session: Session) -> None:
    repository = PostgresOrderRepository(db_session)
    repository.save(SAMPLE_MARKET_ORDER, mode=TradingMode.BACKTEST)
    db_session.commit()

    updated = repository.update_status("order-001", OrderStatus.FILLED)
    db_session.commit()
    assert updated.status == OrderStatus.FILLED


@pytest.mark.integration
def test_order_repository_get_by_id_not_found(db_session: Session) -> None:
    repository = PostgresOrderRepository(db_session)
    with pytest.raises(EntityNotFoundError):
        repository.get_by_id(9999)
