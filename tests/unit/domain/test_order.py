from decimal import Decimal

import pytest

from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.exceptions import DomainValidationError
from app.domain.models.order import Order
from tests.fixtures.orders import SAMPLE_LIMIT_ORDER, SAMPLE_MARKET_ORDER


@pytest.mark.unit
def test_order_defaults() -> None:
    assert SAMPLE_MARKET_ORDER.status == OrderStatus.CREATED
    assert SAMPLE_MARKET_ORDER.side == OrderSide.BUY
    assert SAMPLE_MARKET_ORDER.order_type == OrderType.MARKET


@pytest.mark.unit
def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(DomainValidationError, match="limit orders require limit_price"):
        Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            limit_price=None,
            client_order_id="order-003",
        )


@pytest.mark.unit
def test_market_order_rejects_limit_price() -> None:
    with pytest.raises(DomainValidationError, match="market orders must not include limit_price"):
        Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            limit_price=Decimal("150.00"),
            client_order_id="order-004",
        )


@pytest.mark.unit
def test_order_rejects_non_positive_quantity() -> None:
    with pytest.raises(DomainValidationError, match="quantity must be greater than zero"):
        Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
            order_type=OrderType.MARKET,
            limit_price=None,
            client_order_id="order-005",
        )


@pytest.mark.unit
def test_limit_order_valid() -> None:
    assert SAMPLE_LIMIT_ORDER.limit_price == Decimal("160.00")
