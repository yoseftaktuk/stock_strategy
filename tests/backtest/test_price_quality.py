from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.domain.enums import OrderSide
from app.risk.risk_manager import RiskManager
from app.strategy.momentum import MomentumStrategy
from app.universe.factory import HISTORICAL_SP500
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import TEST_CONFIG, make_series
from tests.fixtures.universe import membership

START = date(2024, 1, 2)
END = date(2024, 3, 21)
GROW_END = date(2024, 2, 10)


def _engine(*, universe=None, universe_kind: str | None = None) -> tuple[BacktestEngine, SimulatedBroker]:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=TEST_CONFIG.lookback_days + 1,
        universe_kind=universe_kind,
    )
    broker = SimulatedBroker(initial_capital=config.initial_capital, commission_rate=Decimal("0"), slippage_bps=Decimal("0"))
    engine = BacktestEngine(
        strategy=MomentumStrategy(TEST_CONFIG),
        broker=broker,
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
        universe_provider=universe,
    )
    return engine, broker


def _qty(result, symbol: str, as_of: date | None = None) -> Decimal:
    orders = {order.client_order_id: order for order in result.orders}
    quantity = Decimal("0")
    for fill in result.fills:
        if fill.symbol != symbol:
            continue
        if as_of is not None and fill.timestamp.date() > as_of:
            continue
        if orders[fill.order_id].side == OrderSide.BUY:
            quantity += fill.quantity
        else:
            quantity -= fill.quantity
    return quantity


def _keep_grow_data() -> dict[str, list]:
    grow_count = (GROW_END - START).days + 1
    keep_count = (END - START).days + 1
    grow_adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(grow_count)]
    keep_adj = [Decimal("100") + Decimal("1") * Decimal(index) for index in range(keep_count)]
    return {
        "GROW": make_series(
            "GROW",
            grow_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=grow_adj,
            volume=2_000_000,
        ),
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
    }


@pytest.mark.backtest
def test_ended_series_is_not_marked_at_last_price() -> None:
    market_data = _keep_grow_data()
    engine, broker = _engine()
    result = engine.run(START, END, market_data=market_data)
    grow_fills = [fill for fill in result.fills if fill.symbol == "GROW"]
    assert grow_fills
    grow_qty = _qty(result, "GROW")
    assert grow_qty > 0
    last_grow = market_data["GROW"][-1]
    last_grow_price = last_grow.close
    keep_closes = {bar.timestamp.date(): bar.close for bar in market_data["KEEP"]}
    after_end = [point for point in result.equity_curve if point.date > GROW_END]
    assert after_end
    assert result.unvalued_symbols == ("GROW",)
    assert any("position left unvalued" in warning for warning in result.warnings)
    assert not any(
        "holding last price" in warning and "symbol=GROW" in warning for warning in result.warnings
    )
    for point in after_end:
        keep_close = keep_closes[point.date]
        keep_qty = _qty(result, "KEEP", point.date)
        grow_held = _qty(result, "GROW", point.date)
        expected = point.cash + keep_close * keep_qty
        stale = expected + last_grow_price * grow_held
        assert point.equity == expected
        assert point.equity != stale
    leftover = {position.symbol: position for position in broker.get_positions()}
    assert leftover["GROW"].valued is False
    assert leftover["GROW"].market_value == Decimal("0")
    quality = result.format_data_quality_report()
    assert "Stale last-price MTM after series end: no" in quality
    assert "GROW" in quality


@pytest.mark.backtest
def test_unusable_identity_series_cannot_fill_and_stays_in_pit() -> None:
    universe = InMemoryUniverseProvider(
        (
            membership("KEEP", date(2010, 1, 1)),
            membership("RICH", date(2010, 1, 1)),
        )
    )
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("1") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
        "RICH": make_series(
            "RICH",
            keep_count,
            start=START,
            close=Decimal("18614.90"),
            volume=2_000_000,
        ),
    }
    engine, _ = _engine(universe=universe, universe_kind=HISTORICAL_SP500)
    result = engine.run(START, END, market_data=market_data)
    assert universe.get_symbols(date(2024, 2, 1)) == ["KEEP", "RICH"]
    assert "RICH" in result.unusable_symbols
    assert "RICH" in result.priced_symbols
    assert all(fill.symbol != "RICH" for fill in result.fills)
    assert result.coverage is not None
    assert result.coverage.unusable_market_data == 1
    assert "PIT membership was not dropped" in " ".join(result.warnings)


@pytest.mark.backtest
def test_extreme_first_price_cannot_fill() -> None:
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("1") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
        "RICH": make_series("RICH", keep_count, start=START, close=Decimal("5000"), volume=2_000_000),
    }
    engine, _ = _engine()
    result = engine.run(START, END, market_data=market_data)
    assert "RICH" in result.unusable_symbols
    assert all(fill.symbol != "RICH" for fill in result.fills)
    assert any("Unusable price series" in warning for warning in result.warnings)


@pytest.mark.backtest
def test_valid_price_series_still_fills() -> None:
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
    }
    engine, _ = _engine()
    result = engine.run(START, END, market_data=market_data)
    assert result.fills
    assert all(fill.symbol == "KEEP" for fill in result.fills)
    assert result.unusable_symbols == ()
    assert result.unvalued_symbols == ()


@pytest.mark.backtest
def test_coverage_separates_missing_unusable_and_valid() -> None:
    universe = InMemoryUniverseProvider(
        (
            membership("KEEP", date(2010, 1, 1)),
            membership("MISS", date(2010, 1, 1)),
            membership("SHORT", date(2010, 1, 1)),
            membership("RICH", date(2010, 1, 1)),
        )
    )
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
        "SHORT": make_series("SHORT", 3, start=START, close=Decimal("50"), volume=2_000_000),
        "RICH": make_series("RICH", keep_count, start=START, close=Decimal("1112"), volume=2_000_000),
    }
    engine, _ = _engine(universe=universe, universe_kind=HISTORICAL_SP500)
    result = engine.run(START, END, market_data=market_data)
    snapshot = result.coverage
    assert snapshot is not None
    assert snapshot.universe_members == 4
    assert snapshot.missing_market_data == 1
    assert snapshot.unusable_market_data == 1
    assert snapshot.insufficient_history == 1
    assert snapshot.market_data_available == 1
    assert "MISS" not in result.priced_symbols
    assert "RICH" in result.priced_symbols
    assert "RICH" in result.unusable_symbols
    assert all(fill.symbol != "RICH" for fill in result.fills)
    assert universe.get_symbols(START) == ["KEEP", "MISS", "RICH", "SHORT"]
    report = result.format_report()
    assert "Unusable Market Data:" in report
    quality = result.format_data_quality_report()
    assert "Unusable symbols: RICH" in quality
    assert "Research readiness: NOT READY" in quality


@pytest.mark.backtest
def test_intra_series_gap_still_holds_last_price() -> None:
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("1") * Decimal(index) for index in range(keep_count)]
    grow_count = keep_count
    grow_adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(grow_count)]
    grow = make_series(
        "GROW",
        grow_count,
        start=START,
        close=Decimal("50"),
        adjusted_closes=grow_adj,
        volume=2_000_000,
    )
    gap_date = date(2024, 2, 15)
    grow = [bar for bar in grow if bar.timestamp.date() != gap_date]
    market_data = {
        "GROW": grow,
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
    }
    engine, _ = _engine()
    result = engine.run(START, END, market_data=market_data)
    assert any("holding last price" in warning and "symbol=GROW" in warning for warning in result.warnings)
    assert "GROW" not in result.unvalued_symbols
    gap_point = next(point for point in result.equity_curve if point.date == gap_date)
    grow_qty = _qty(result, "GROW", gap_date)
    keep_qty = _qty(result, "KEEP", gap_date)
    keep_close = next(bar.close for bar in market_data["KEEP"] if bar.timestamp.date() == gap_date)
    prior = next(bar for bar in reversed(grow) if bar.timestamp.date() < gap_date)
    expected = gap_point.cash + keep_close * keep_qty + prior.close * grow_qty
    assert gap_point.equity == expected
