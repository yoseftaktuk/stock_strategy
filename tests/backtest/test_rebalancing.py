from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.domain.enums import OrderSide
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position
from app.domain.models.target import TargetPortfolio, TargetPosition


@pytest.mark.backtest
def test_sell_before_buy_when_names_rotate() -> None:
    current = Portfolio(
        cash=Decimal("80000"),
        positions=(
            Position("AAPL", Decimal("100"), Decimal("100"), Decimal("100")),
            Position("MSFT", Decimal("100"), Decimal("100"), Decimal("100")),
        ),
    )
    target = TargetPortfolio(
        positions=(
            TargetPosition("MSFT", Decimal("0.10")),
            TargetPosition("NVDA", Decimal("0.10")),
        ),
        cash_weight=Decimal("0.80"),
    )
    orders = OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")).create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100"), "MSFT": Decimal("100"), "NVDA": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    sides = [order.side for order in orders]
    assert OrderSide.SELL in sides
    assert OrderSide.BUY in sides
    assert sides.index(OrderSide.SELL) < sides.index(OrderSide.BUY)
    assert [order.symbol for order in orders if order.side == OrderSide.SELL] == ["AAPL"]
    assert [order.symbol for order in orders if order.side == OrderSide.BUY] == ["NVDA"]
