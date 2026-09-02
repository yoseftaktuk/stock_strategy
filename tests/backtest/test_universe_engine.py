from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.domain.models.market_bar import MarketBar
from app.domain.models.signal import MomentumSignal
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import make_series
from tests.fixtures.universe import survivorship_memberships

START = date(2015, 1, 2)
END = date(2015, 3, 31)


class RecordingStrategy(Strategy):
    def __init__(self) -> None:
        self.seen: list[tuple[date, tuple[str, ...]]] = []

    def generate_signals(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> list[MomentumSignal]:
        self.seen.append((as_of, tuple(sorted(market_data))))
        return []


def _engine(strategy: Strategy, provider: InMemoryUniverseProvider | None) -> BacktestEngine:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=1,
        symbols=("AAA", "BBB", "ZZZ"),
    )
    return BacktestEngine(
        strategy=strategy,
        broker=SimulatedBroker(initial_capital=config.initial_capital),
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
        universe_provider=provider,
    )


@pytest.mark.backtest
def test_engine_filters_market_data_to_point_in_time_universe() -> None:
    market_data = {
        "AAA": make_series("AAA", 60, start=START, close=Decimal("50")),
        "BBB": make_series("BBB", 60, start=START, close=Decimal("50")),
        "ZZZ": make_series("ZZZ", 60, start=START, close=Decimal("50")),
    }
    strategy = RecordingStrategy()
    engine = _engine(strategy, InMemoryUniverseProvider(survivorship_memberships()))
    result = engine.run(START, END, market_data=market_data)
    assert strategy.seen
    for _as_of, symbols in strategy.seen:
        assert symbols == ("AAA", "BBB")
        assert "ZZZ" not in symbols
        assert "EEE" not in symbols
    missing_warnings = [warning for warning in result.warnings if "Missing market data" in warning]
    assert len(missing_warnings) == 1
    assert "CCC" in missing_warnings[0]
    assert "Universe membership was not dropped" in missing_warnings[0]


@pytest.mark.backtest
def test_engine_without_provider_keeps_loaded_symbols() -> None:
    market_data = {
        "AAA": make_series("AAA", 60, start=START, close=Decimal("50")),
        "ZZZ": make_series("ZZZ", 60, start=START, close=Decimal("50")),
    }
    strategy = RecordingStrategy()
    engine = _engine(strategy, None)
    engine.run(START, END, market_data=market_data)
    assert strategy.seen
    for _as_of, symbols in strategy.seen:
        assert symbols == ("AAA", "ZZZ")
