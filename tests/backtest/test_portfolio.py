from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.domain.enums import OrderSide
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position
from app.domain.models.signal import MomentumSignal
from app.domain.models.target import TargetPortfolio, TargetPosition


def _signal(symbol: str, rank: int) -> MomentumSignal:
    return MomentumSignal(
        symbol=symbol,
        date=date(2024, 2, 1),
        momentum=Decimal("0.20"),
        rank=rank,
        eligible=True,
    )


@pytest.mark.backtest
def test_equal_weight_ten_percent() -> None:
    signals = [_signal(symbol, rank) for rank, symbol in enumerate(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"], start=1)]
    target = PortfolioService().build_target_portfolio(signals)
    assert len(target.positions) == 10
    assert all(item.target_weight == Decimal("0.1") for item in target.positions)
    assert target.cash_weight == Decimal("0")


@pytest.mark.backtest
def test_equal_weight_seven_names() -> None:
    signals = [_signal(f"S{index}", index) for index in range(1, 8)]
    target = PortfolioService().build_target_portfolio(signals)
    assert len(target.positions) == 7
    expected = Decimal("1") / Decimal("7")
    assert target.positions[0].target_weight == expected
    assert target.cash_weight == Decimal("1") - expected * 7


@pytest.mark.backtest
def test_empty_signals_are_all_cash() -> None:
    target = PortfolioService().build_target_portfolio([])
    assert target.positions == ()
    assert target.cash_weight == Decimal("1")


def _portfolio(*positions: Position, cash: Decimal = Decimal("100000")) -> Portfolio:
    return Portfolio(cash=cash, positions=positions)


def _order_service() -> OrderService:
    return OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0"))


@pytest.mark.backtest
def test_new_position_buy_at_ten_percent() -> None:
    current = _portfolio()
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.10")),),
        cash_weight=Decimal("0.90"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BUY
    assert orders[0].quantity == Decimal("100")


@pytest.mark.backtest
def test_twenty_percent_target() -> None:
    current = _portfolio()
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.20")),),
        cash_weight=Decimal("0.80"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert orders[0].quantity == Decimal("200")


@pytest.mark.backtest
def test_zero_target_exits_position() -> None:
    current = _portfolio(
        Position("AAPL", Decimal("100"), Decimal("100"), Decimal("100")),
        cash=Decimal("0"),
    )
    target = TargetPortfolio(positions=(), cash_weight=Decimal("1"))
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert len(orders) == 1
    assert orders[0].side == OrderSide.SELL
    assert orders[0].quantity == Decimal("100")


@pytest.mark.backtest
def test_partial_rebalance_buys_the_difference() -> None:
    current = _portfolio(
        Position("AAPL", Decimal("50"), Decimal("100"), Decimal("100")),
        cash=Decimal("95000"),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.10")),),
        cash_weight=Decimal("0.90"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert orders[0].side == OrderSide.BUY
    assert orders[0].quantity == Decimal("50")


@pytest.mark.backtest
def test_partial_rebalance_sells_the_difference() -> None:
    current = _portfolio(
        Position("AAPL", Decimal("150"), Decimal("100"), Decimal("100")),
        cash=Decimal("85000"),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.10")),),
        cash_weight=Decimal("0.90"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert orders[0].side == OrderSide.SELL
    assert orders[0].quantity == Decimal("50")


@pytest.mark.backtest
def test_unchanged_weight_does_not_generate_orders() -> None:
    current = _portfolio(
        Position("AAPL", Decimal("100"), Decimal("100"), Decimal("100")),
        cash=Decimal("90000"),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.10")),),
        cash_weight=Decimal("0.90"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2024, 2, 1),
    )
    assert orders == []


@pytest.mark.backtest
def test_min_trade_value_skips_tiny_diff() -> None:
    current = _portfolio(
        Position("AAPL", Decimal("100"), Decimal("100"), Decimal("100")),
        cash=Decimal("90000"),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("AAPL", Decimal("0.1005")),),
        cash_weight=Decimal("0.8995"),
    )
    orders = _order_service().create_orders_from_targets(
        current,
        target,
        {"AAPL": Decimal("100")},
        min_trade_value=Decimal("100"),
        as_of=date(2024, 2, 1),
    )
    assert orders == []
