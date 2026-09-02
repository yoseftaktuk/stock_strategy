from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.diagnostics import CURRENT_UNIVERSE_WARNING
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.risk.risk_manager import RiskManager
from app.strategy.momentum import MomentumStrategy
from app.universe.factory import HISTORICAL_SP500
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import TEST_CONFIG, make_series
from tests.fixtures.universe import membership

START = date(2015, 1, 2)
END = date(2015, 3, 31)


def _engine() -> BacktestEngine:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=1,
        universe_kind=HISTORICAL_SP500,
    )
    return BacktestEngine(
        strategy=MomentumStrategy(TEST_CONFIG),
        broker=SimulatedBroker(initial_capital=config.initial_capital),
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
        universe_provider=InMemoryUniverseProvider(
            (
                membership("AAA", date(2010, 1, 1)),
                membership("BBB", date(2010, 1, 1)),
                membership("CCC", date(2010, 1, 1)),
            )
        ),
    )


@pytest.mark.backtest
def test_coverage_snapshot_separates_missing_and_insufficient_history() -> None:
    rising = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(90)]
    market_data = {
        "AAA": make_series(
            "AAA",
            90,
            start=START,
            close=Decimal("50"),
            adjusted_closes=rising,
            volume=2_000_000,
        ),
        "CCC": make_series("CCC", 3, start=START, close=Decimal("50"), volume=2_000_000),
    }
    result = _engine().run(START, END, market_data=market_data)
    snapshot = result.coverage
    assert snapshot is not None
    assert snapshot.universe_members == 3
    assert snapshot.market_data_available == 1
    assert snapshot.missing_market_data == 1
    assert snapshot.insufficient_history == 1
    assert "BBB" not in result.priced_symbols
    assert "CCC" in result.priced_symbols
    assert snapshot.warning is not None
    assert "membership is applied" in snapshot.warning
    assert "NOT a full S&P 500 historical backtest" in snapshot.warning
    assert CURRENT_UNIVERSE_WARNING not in result.warnings
    assert "Universe membership was not dropped" in " ".join(result.warnings)
