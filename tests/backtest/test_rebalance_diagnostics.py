from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.risk.risk_manager import RiskManager
from app.strategy.momentum import MomentumStrategy
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import TEST_CONFIG, make_series
from tests.fixtures.universe import membership

START = date(2015, 1, 2)
END = date(2015, 3, 31)


def _engine(provider: InMemoryUniverseProvider) -> BacktestEngine:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=1,
        universe_kind="historical_sp500",
    )
    return BacktestEngine(
        strategy=MomentumStrategy(TEST_CONFIG),
        broker=SimulatedBroker(initial_capital=config.initial_capital),
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
        universe_provider=provider,
    )


@pytest.mark.backtest
def test_rebalance_diagnostics_separate_missing_history_and_filters() -> None:
    provider = InMemoryUniverseProvider(
        (
            membership("AAA", date(2010, 1, 1)),
            membership("BBB", date(2010, 1, 1)),
            membership("CCC", date(2010, 1, 1)),
            membership("DDD", date(2010, 1, 1)),
            membership("EEE", date(2010, 1, 1)),
            membership("FFF", date(2010, 1, 1)),
        )
    )
    rising = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(90)]
    falling = [Decimal("200") - Decimal("2") * Decimal(index) for index in range(90)]
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
        "DDD": make_series("DDD", 90, start=START, close=Decimal("5"), volume=2_000_000),
        "EEE": make_series("EEE", 90, start=START, close=Decimal("50"), volume=1),
        "FFF": make_series(
            "FFF",
            90,
            start=START,
            close=Decimal("50"),
            adjusted_closes=falling,
            volume=2_000_000,
        ),
    }
    result = _engine(provider).run(START, END, market_data=market_data)
    assert result.rebalance_diagnostics
    for row in result.rebalance_diagnostics:
        assert row.universe_members == 6
        assert row.missing_market_data == 1
        assert row.insufficient_history == 1
        assert row.failed_price_filter == 1
        assert row.failed_liquidity_filter == 1
        assert row.momentum_eligible == 1
        assert row.selected == 1
    assert result.missing_price_count == 1
    assert "BBB" not in result.priced_symbols
    assert "Universe membership was not dropped" in " ".join(result.warnings)
