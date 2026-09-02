from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.diagnostics import CURRENT_UNIVERSE_WARNING
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.domain.models.market_bar import MarketBar
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy
from app.strategy.momentum import MomentumStrategy
from app.universe.factory import CURRENT, HISTORICAL_SP500
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import TEST_CONFIG, make_series
from tests.fixtures.universe import late_entrant_memberships, membership, survivorship_memberships

START_2015 = date(2015, 1, 2)
END_2015 = date(2015, 3, 31)
START_2020 = date(2020, 1, 2)
END_2020 = date(2020, 3, 31)
START_2025 = date(2025, 1, 2)
END_2025 = date(2025, 3, 31)
COUNT = 90


class RecordingMomentum(MomentumStrategy):
    def __init__(self) -> None:
        super().__init__(TEST_CONFIG)
        self.seen: list[tuple[date, tuple[str, ...]]] = []
        self.selected: list[tuple[date, tuple[str, ...]]] = []

    def evaluate(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ):
        evaluation = super().evaluate(market_data, as_of)
        self.seen.append((as_of, tuple(sorted(market_data))))
        self.selected.append((as_of, evaluation.selected_symbols))
        return evaluation


def _sloped_series(symbol: str, start: date, slope: Decimal) -> list:
    adjusted = [Decimal("100") + slope * Decimal(index) for index in range(COUNT)]
    return make_series(
        symbol,
        COUNT,
        start=start,
        close=Decimal("50"),
        adjusted_closes=adjusted,
        volume=2_000_000,
    )


def _engine(
    strategy: Strategy,
    provider: InMemoryUniverseProvider | None,
    start: date,
    end: date,
    *,
    universe_kind: str | None = None,
) -> BacktestEngine:
    config = BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=1,
        universe_kind=universe_kind,
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


def _selected(strategy: RecordingMomentum) -> set[str]:
    names: set[str] = set()
    for _as_of, symbols in strategy.selected:
        names.update(symbols)
    return names


@pytest.mark.backtest
def test_point_in_time_universe_is_queried_independently_each_year() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    cases = (
        (START_2015, END_2015, ("AAA", "BBB", "CCC")),
        (START_2020, END_2020, ("AAA", "CCC", "DDD")),
        (START_2025, END_2025, ("AAA", "DDD", "EEE")),
    )
    for start, end, expected in cases:
        market_data = {
            symbol: _sloped_series(symbol, start, Decimal("1"))
            for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "ZZZ")
        }
        strategy = RecordingMomentum()
        _engine(strategy, provider, start, end).run(start, end, market_data=market_data)
        assert strategy.seen
        for _as_of, symbols in strategy.seen:
            assert symbols == expected
            assert "ZZZ" not in symbols


@pytest.mark.backtest
def test_future_member_cannot_be_selected_even_with_strong_momentum() -> None:
    """Classic survivorship bug: AAA is current, strong in 2015, entered only in 2020."""
    market_data = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("5")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("1")),
        "CCC": _sloped_series("CCC", START_2015, Decimal("0.5")),
    }
    historical = RecordingMomentum()
    _engine(
        historical,
        InMemoryUniverseProvider(late_entrant_memberships()),
        START_2015,
        END_2015,
        universe_kind=HISTORICAL_SP500,
    ).run(START_2015, END_2015, market_data=market_data)
    assert historical.seen
    for _as_of, symbols in historical.seen:
        assert "AAA" not in symbols
        assert symbols == ("BBB", "CCC")
    assert "AAA" not in _selected(historical)
    assert _selected(historical)

    current = RecordingMomentum()
    _engine(
        current,
        InMemoryUniverseProvider(late_entrant_memberships(), current_only=True),
        START_2015,
        END_2015,
        universe_kind=CURRENT,
    ).run(START_2015, END_2015, market_data=market_data)
    assert current.seen
    for _as_of, symbols in current.seen:
        assert "AAA" in symbols
    assert "AAA" in _selected(current)


@pytest.mark.backtest
def test_removed_constituent_can_be_selected_only_while_a_member() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    data_2015 = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("1")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("5")),
        "CCC": _sloped_series("CCC", START_2015, Decimal("0.5")),
    }
    strategy_2015 = RecordingMomentum()
    _engine(strategy_2015, provider, START_2015, END_2015).run(
        START_2015, END_2015, market_data=data_2015
    )
    assert "BBB" in _selected(strategy_2015)
    for _as_of, symbols in strategy_2015.seen:
        assert "BBB" in symbols

    data_2020 = {
        "AAA": _sloped_series("AAA", START_2020, Decimal("1")),
        "BBB": _sloped_series("BBB", START_2020, Decimal("5")),
        "CCC": _sloped_series("CCC", START_2020, Decimal("2")),
        "DDD": _sloped_series("DDD", START_2020, Decimal("0.5")),
    }
    strategy_2020 = RecordingMomentum()
    _engine(strategy_2020, provider, START_2020, END_2020).run(
        START_2020, END_2020, market_data=data_2020
    )
    assert "BBB" not in _selected(strategy_2020)
    for _as_of, symbols in strategy_2020.seen:
        assert "BBB" not in symbols
        assert symbols == ("AAA", "CCC", "DDD")


@pytest.mark.backtest
def test_open_ended_membership_remains_eligible() -> None:
    provider = InMemoryUniverseProvider([membership("AAA", date(2010, 1, 1), None)])
    market_data = {"AAA": _sloped_series("AAA", START_2025, Decimal("1"))}
    strategy = RecordingMomentum()
    _engine(strategy, provider, START_2025, END_2025).run(
        START_2025, END_2025, market_data=market_data
    )
    assert strategy.seen
    for _as_of, symbols in strategy.seen:
        assert symbols == ("AAA",)
    assert "AAA" in _selected(strategy)


@pytest.mark.backtest
def test_current_universe_warning_is_in_the_report() -> None:
    market_data = {"AAA": _sloped_series("AAA", START_2015, Decimal("1"))}
    result = _engine(
        RecordingMomentum(),
        InMemoryUniverseProvider(late_entrant_memberships(), current_only=True),
        START_2015,
        END_2015,
        universe_kind=CURRENT,
    ).run(START_2015, END_2015, market_data=market_data)
    assert CURRENT_UNIVERSE_WARNING in result.warnings
    report = result.format_report()
    assert "Universe:" in report
    assert "\ncurrent\n" in report
    assert "SURVIVORSHIP-BIASED FOR HISTORICAL BACKTESTING" in report


@pytest.mark.backtest
def test_historical_universe_label_in_report() -> None:
    market_data = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("1")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("1")),
    }
    result = _engine(
        RecordingMomentum(),
        InMemoryUniverseProvider(survivorship_memberships()),
        START_2015,
        END_2015,
        universe_kind=HISTORICAL_SP500,
    ).run(START_2015, END_2015, market_data=market_data)
    report = result.format_report()
    assert "Universe:" in report
    assert "Historical S&P 500 Point-in-Time" in report
    assert CURRENT_UNIVERSE_WARNING not in report


@pytest.mark.backtest
def test_verbose_report_includes_computed_rebalance_diagnostics() -> None:
    market_data = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("1")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("1")),
    }
    result = _engine(
        RecordingMomentum(),
        InMemoryUniverseProvider(survivorship_memberships()),
        START_2015,
        END_2015,
        universe_kind=HISTORICAL_SP500,
    ).run(START_2015, END_2015, market_data=market_data)
    assert result.rebalance_diagnostics
    compact = result.format_report()
    assert "Universe Members:" not in compact
    verbose = result.format_report(verbose=True)
    first = result.rebalance_diagnostics[0]
    assert f"Rebalance: {first.as_of.isoformat()}" in verbose
    assert f"Universe Members: {first.universe_members}" in verbose
    assert first.universe_members == 3
    assert first.missing_market_data == 1
    assert first.selected >= 1


@pytest.mark.backtest
def test_survivorship_backtest_is_deterministic() -> None:
    market_data = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("2")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("5")),
        "CCC": _sloped_series("CCC", START_2015, Decimal("1")),
    }
    provider = InMemoryUniverseProvider(survivorship_memberships())
    first_strategy = RecordingMomentum()
    second_strategy = RecordingMomentum()
    first = _engine(first_strategy, provider, START_2015, END_2015).run(
        START_2015, END_2015, market_data=market_data
    )
    second = _engine(second_strategy, provider, START_2015, END_2015).run(
        START_2015, END_2015, market_data=market_data
    )
    assert first.equity_curve == second.equity_curve
    assert first.fills == second.fills
    assert first_strategy.selected == second_strategy.selected
    assert first.rebalance_diagnostics == second.rebalance_diagnostics


@pytest.mark.backtest
def test_pit_pipeline_smoke_produces_equity_and_metrics() -> None:
    market_data = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("2")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("5")),
        "CCC": _sloped_series("CCC", START_2015, Decimal("1")),
    }
    result = _engine(
        RecordingMomentum(),
        InMemoryUniverseProvider(survivorship_memberships()),
        START_2015,
        END_2015,
        universe_kind=HISTORICAL_SP500,
    ).run(START_2015, END_2015, market_data=market_data)
    assert result.equity_curve
    assert result.final_equity > 0
    assert result.number_of_trades > 0
    assert result.rebalance_diagnostics
    assert result.universe_kind == HISTORICAL_SP500
    assert result.orders


@pytest.mark.backtest
def test_market_data_availability_does_not_override_pit_membership() -> None:
    provider = InMemoryUniverseProvider(
        (
            membership("AAA", date(2010, 1, 1), date(2020, 1, 1)),
            membership("BBB", date(2020, 1, 1), None),
        )
    )
    data_2015 = {
        "AAA": _sloped_series("AAA", START_2015, Decimal("1")),
        "BBB": _sloped_series("BBB", START_2015, Decimal("5")),
    }
    strategy_2015 = RecordingMomentum()
    _engine(strategy_2015, provider, START_2015, END_2015, universe_kind=HISTORICAL_SP500).run(
        START_2015, END_2015, market_data=data_2015
    )
    assert strategy_2015.seen
    for _as_of, symbols in strategy_2015.seen:
        assert "AAA" in symbols
        assert "BBB" not in symbols
    assert "AAA" in _selected(strategy_2015)
    assert "BBB" not in _selected(strategy_2015)

    data_2025 = {
        "AAA": _sloped_series("AAA", START_2025, Decimal("5")),
        "BBB": _sloped_series("BBB", START_2025, Decimal("1")),
    }
    strategy_2025 = RecordingMomentum()
    _engine(strategy_2025, provider, START_2025, END_2025, universe_kind=HISTORICAL_SP500).run(
        START_2025, END_2025, market_data=data_2025
    )
    assert strategy_2025.seen
    for _as_of, symbols in strategy_2025.seen:
        assert "BBB" in symbols
        assert "AAA" not in symbols
    assert "BBB" in _selected(strategy_2025)
    assert "AAA" not in _selected(strategy_2025)
