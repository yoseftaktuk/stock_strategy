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
from tests.fixtures.universe import membership, survivorship_memberships

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


@pytest.mark.backtest
def test_universe_as_of_is_signal_date_not_execution_date() -> None:
    """A name that becomes a member on the execution date must not be in the signal universe."""
    signal_date = date(2015, 2, 1)
    execution_date = date(2015, 2, 2)
    provider = InMemoryUniverseProvider(
        (
            membership("AAA", date(2010, 1, 1)),
            membership("NEW", execution_date),
        )
    )
    market_data = {
        "AAA": make_series("AAA", 60, start=START, close=Decimal("50")),
        "NEW": make_series("NEW", 60, start=START, close=Decimal("50")),
    }
    strategy = RecordingStrategy()
    engine = _engine(strategy, provider)
    engine.run(START, END, market_data=market_data)
    seen_on_signal = [symbols for as_of, symbols in strategy.seen if as_of == signal_date]
    assert seen_on_signal
    assert "NEW" not in seen_on_signal[0]
    assert "AAA" in seen_on_signal[0]
    seen_on_execution_month = [symbols for as_of, symbols in strategy.seen if as_of >= execution_date]
    assert any("NEW" in symbols for symbols in seen_on_execution_month)
