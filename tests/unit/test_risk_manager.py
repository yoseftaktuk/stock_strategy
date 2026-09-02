from decimal import Decimal

import pytest

from app.domain.enums import OrderSide, OrderType
from app.domain.models.order import Order
from app.risk.risk_manager import RiskManager
from tests.fixtures.portfolios import SAMPLE_PORTFOLIO


@pytest.mark.unit
def test_risk_manager_validate_returns_true() -> None:
    risk_manager = RiskManager()
    order = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="test-001",
    )
    assert risk_manager.validate(order, SAMPLE_PORTFOLIO) is True


@pytest.mark.unit
def test_risk_manager_rejects_short_sale() -> None:
    risk_manager = RiskManager()
    order = Order(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=Decimal("1000"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="test-short",
    )
    assert risk_manager.validate(order, SAMPLE_PORTFOLIO) is False
