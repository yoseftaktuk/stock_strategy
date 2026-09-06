from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.data import warmup_history_start
from app.backtest.engine import BacktestEngine, _monthly_rebalance_dates
from app.backtest.exceptions import BacktestConfigError
from app.backtest.metrics import CALENDAR_DAYS_PER_YEAR
from app.backtest.warmup import resolve_warmup_bounds
from app.broker.simulated import SimulatedBroker
from app.domain.models.market_bar import MarketBar
from app.domain.models.signal import MomentumSignal
from app.domain.models.target import TargetPortfolio
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy
from app.strategy.config import MomentumConfig
from app.strategy.momentum import MomentumStrategy
from tests.fixtures.momentum import TEST_CONFIG, make_series

START = date(2024, 1, 2)
END = date(2024, 4, 30)
SIGNAL_START = date(2024, 3, 1)
LOOKBACK_252_START = date(2020, 1, 2)
LOOKBACK_252_END = date(2020, 3, 31)
PRE_HISTORY_START = date(2019, 4, 1)

LONG_CONFIG = MomentumConfig(
    lookback_days=252,
    skip_days=21,
    top_n=2,
    min_price=Decimal("10"),
    liquidity_window_days=20,
    min_dollar_volume=Decimal("1000"),
)


class RecordingMomentum(Strategy):
    def __init__(self, inner: MomentumStrategy) -> None:
        self._inner = inner
        self.seen: list[tuple[date, dict[str, tuple[date, ...]], tuple[MomentumSignal, ...]]] = []

    @property
    def config(self) -> MomentumConfig:
        return self._inner.config

    def generate_signals(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> list[MomentumSignal]:
        return self.evaluate(market_data, as_of).signals

    def evaluate(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ):
        snapshot = {
            symbol: tuple(bar.timestamp.date() for bar in bars)
            for symbol, bars in market_data.items()
        }
        evaluation = self._inner.evaluate(market_data, as_of)
        self.seen.append((as_of, snapshot, tuple(evaluation.signals)))
        return evaluation


class RecordingPortfolioService(PortfolioService):
    def __init__(self) -> None:
        self.targets: list[TargetPortfolio] = []

    def build_target_portfolio(self, signals: Sequence[MomentumSignal]) -> TargetPortfolio:
        target = super().build_target_portfolio(signals)
        self.targets.append(target)
        return target


def _sloped_series(symbol: str, count: int, start: date, slope: Decimal) -> list:
    closes = [Decimal("50") + slope * Decimal(index) for index in range(count)]
    return make_series(
        symbol,
        count,
        start=start,
        close=Decimal("50"),
        closes=closes,
        adjusted_closes=closes,
        volume=2_000_000,
    )


def _market_data(*, start: date, count: int) -> dict[str, list]:
    return {
        "NVDA": _sloped_series("NVDA", count, start, Decimal("2")),
        "MSFT": _sloped_series("MSFT", count, start, Decimal("1.5")),
    }


def _config(**kwargs: object) -> BacktestConfig:
    values: dict[str, object] = {
        "start_date": START,
        "end_date": END,
        "initial_capital": Decimal("100000"),
        "commission_rate": Decimal("0"),
        "slippage_bps": Decimal("0"),
        "min_trade_value": Decimal("1"),
        "warmup_sessions": TEST_CONFIG.lookback_days + 1,
    }
    values.update(kwargs)
    return BacktestConfig(**values)  # type: ignore[arg-type]


def _engine(
    config: BacktestConfig,
    strategy: Strategy,
    portfolio: PortfolioService | None = None,
) -> tuple[BacktestEngine, RecordingPortfolioService]:
    recorded = portfolio if isinstance(portfolio, RecordingPortfolioService) else RecordingPortfolioService()
    engine = BacktestEngine(
        strategy=strategy,
        broker=SimulatedBroker(
            initial_capital=config.initial_capital,
            commission_rate=config.commission_rate,
            slippage_bps=config.slippage_bps,
        ),
        portfolio_service=recorded,
        order_service=OrderService(
            commission_rate=config.commission_rate,
            slippage_bps=config.slippage_bps,
        ),
        risk_manager=RiskManager(),
        config=config,
    )
    return engine, recorded


def _order_dates(result) -> set[date]:
    dates: set[date] = set()
    for order in result.orders:
        dates.add(date.fromisoformat(order.client_order_id[:10]))
    return dates


@pytest.mark.backtest
def test_resolve_warmup_bounds_legacy_keeps_in_window_gate() -> None:
    bounds = resolve_warmup_bounds(
        start=date(2015, 1, 1),
        end=date(2025, 12, 31),
        lookback_days=252,
        signal_start=None,
        warmup_sessions=253,
    )
    assert bounds.mode == "legacy"
    assert bounds.calendar_start == date(2015, 1, 1)
    assert bounds.performance_start == date(2015, 1, 1)
    assert bounds.signal_start is None
    assert bounds.in_window_warmup_sessions == 253
    assert bounds.warmup_start == warmup_history_start(date(2015, 1, 1), 252)


@pytest.mark.backtest
def test_resolve_warmup_bounds_explicit_signal_drops_in_window_gate() -> None:
    bounds = resolve_warmup_bounds(
        start=date(2015, 1, 1),
        end=date(2025, 12, 31),
        lookback_days=252,
        signal_start=date(2020, 1, 1),
        warmup_sessions=253,
    )
    assert bounds.mode == "explicit_signal"
    assert bounds.signal_start == date(2020, 1, 1)
    assert bounds.performance_start == date(2020, 1, 1)
    assert bounds.calendar_start == date(2015, 1, 1)
    assert bounds.in_window_warmup_sessions == 1
    assert bounds.warmup_start == warmup_history_start(date(2015, 1, 1), 252)


@pytest.mark.backtest
def test_signal_start_before_start_is_rejected() -> None:
    with pytest.raises(BacktestConfigError, match="signal_start must be >= start_date"):
        BacktestConfig(
            start_date=START,
            end_date=END,
            signal_start=date(2023, 12, 1),
        )


@pytest.mark.backtest
def test_signal_start_after_end_is_rejected() -> None:
    with pytest.raises(BacktestConfigError, match="signal_start must be <= end_date"):
        BacktestConfig(
            start_date=START,
            end_date=END,
            signal_start=date(2025, 1, 1),
        )


@pytest.mark.backtest
def test_lookback_history_before_signal_start_is_visible_and_as_of_capped() -> None:
    lookback_need = LONG_CONFIG.lookback_days + 1
    pre_count = lookback_need + 10
    calendar_count = 80
    pre = _market_data(start=PRE_HISTORY_START, count=pre_count)
    window = _market_data(start=LOOKBACK_252_START, count=calendar_count)
    market_data = {
        symbol: pre[symbol] + window[symbol]
        for symbol in pre
    }
    strategy = RecordingMomentum(MomentumStrategy(LONG_CONFIG))
    config = _config(
        start_date=LOOKBACK_252_START,
        end_date=LOOKBACK_252_END,
        warmup_sessions=lookback_need,
        signal_start=LOOKBACK_252_START,
    )
    engine, portfolio = _engine(config, strategy)
    result = engine.run(LOOKBACK_252_START, LOOKBACK_252_END, market_data=market_data)

    assert strategy.seen
    first_as_of, snapshot, signals = strategy.seen[0]
    assert first_as_of == LOOKBACK_252_START
    assert result.first_signal_date == LOOKBACK_252_START
    assert signals
    for symbol, dates in snapshot.items():
        assert dates
        assert min(dates) < LOOKBACK_252_START
        assert PRE_HISTORY_START in dates
        assert max(dates) <= first_as_of
        assert all(session <= first_as_of for session in dates)
        future = [bar.timestamp.date() for bar in market_data[symbol] if bar.timestamp.date() > first_as_of]
        assert future
        assert set(future).isdisjoint(dates)
        assert len([session for session in dates if session <= first_as_of]) >= lookback_need
    assert portfolio.targets
    assert any(target.positions for target in portfolio.targets)


@pytest.mark.backtest
def test_explicit_signal_does_not_wait_in_window_warmup_when_history_exists() -> None:
    lookback_need = LONG_CONFIG.lookback_days + 1
    pre = _market_data(start=PRE_HISTORY_START, count=lookback_need + 10)
    window = _market_data(start=LOOKBACK_252_START, count=90)
    market_data = {symbol: pre[symbol] + window[symbol] for symbol in pre}

    legacy_strategy = RecordingMomentum(MomentumStrategy(LONG_CONFIG))
    legacy_config = _config(
        start_date=LOOKBACK_252_START,
        end_date=LOOKBACK_252_END,
        warmup_sessions=lookback_need,
    )
    legacy_engine, _ = _engine(legacy_config, legacy_strategy)
    legacy = legacy_engine.run(LOOKBACK_252_START, LOOKBACK_252_END, market_data=market_data)

    explicit_strategy = RecordingMomentum(MomentumStrategy(LONG_CONFIG))
    explicit_config = _config(
        start_date=LOOKBACK_252_START,
        end_date=LOOKBACK_252_END,
        warmup_sessions=lookback_need,
        signal_start=LOOKBACK_252_START,
    )
    explicit_engine, _ = _engine(explicit_config, explicit_strategy)
    explicit = explicit_engine.run(LOOKBACK_252_START, LOOKBACK_252_END, market_data=market_data)

    assert not legacy.rebalance_diagnostics
    assert "warmup sessions" in legacy.warnings[0]
    assert explicit.first_signal_date == LOOKBACK_252_START
    assert explicit.rebalance_diagnostics[0].as_of == LOOKBACK_252_START
    assert explicit_strategy.seen[0][2]


@pytest.mark.backtest
def test_no_signal_target_order_or_fill_before_signal_start() -> None:
    market_data = _market_data(start=date(2023, 12, 1), count=160)
    strategy = RecordingMomentum(MomentumStrategy(TEST_CONFIG))
    config = _config(signal_start=SIGNAL_START)
    engine, portfolio = _engine(config, strategy)
    result = engine.run(START, END, market_data=market_data)

    assert strategy.seen
    for as_of, _snapshot, signals in strategy.seen:
        assert as_of >= SIGNAL_START
        assert all(signal.date >= SIGNAL_START for signal in signals)
    assert len(portfolio.targets) == len(strategy.seen)
    assert result.first_signal_date == SIGNAL_START
    assert all(row.as_of >= SIGNAL_START for row in result.rebalance_diagnostics)
    assert all(fill.timestamp.date() >= SIGNAL_START for fill in result.fills)
    assert all(session >= SIGNAL_START for session in _order_dates(result))
    trading_dates = sorted(
        {bar.timestamp.date() for bars in market_data.values() for bar in bars if START <= bar.timestamp.date() <= END}
    )
    legacy_rebalances = _monthly_rebalance_dates(trading_dates, TEST_CONFIG.lookback_days + 1)
    assert date(2024, 2, 1) in legacy_rebalances
    assert date(2024, 2, 1) not in {row.as_of for row in result.rebalance_diagnostics}


@pytest.mark.backtest
def test_performance_measurement_starts_at_signal_start() -> None:
    market_data = _market_data(start=date(2023, 12, 1), count=160)
    strategy = RecordingMomentum(MomentumStrategy(TEST_CONFIG))
    config = _config(signal_start=SIGNAL_START)
    engine, _ = _engine(config, strategy)
    result = engine.run(START, END, market_data=market_data)

    assert result.signal_start == SIGNAL_START
    assert result.equity_curve
    assert result.equity_curve[0].date >= SIGNAL_START
    assert all(point.date >= SIGNAL_START for point in result.equity_curve)
    assert result.equity_curve[0].equity == config.initial_capital
    assert result.equity_curve[0].drawdown == Decimal("0")
    years = max((END - SIGNAL_START).days, 0) / CALENDAR_DAYS_PER_YEAR
    expected = (float(result.final_equity / result.initial_capital) ** (1 / years)) - 1
    assert result.annualized_return == pytest.approx(expected)
    wrong_years = max((END - START).days, 0) / CALENDAR_DAYS_PER_YEAR
    wrong = (float(result.final_equity / result.initial_capital) ** (1 / wrong_years)) - 1
    assert result.annualized_return != pytest.approx(wrong)
    assert "Signal start:\n2024-03-01" in result.format_report()


@pytest.mark.backtest
def test_legacy_start_end_keeps_in_window_warmup_and_equity_from_start() -> None:
    market_data = _market_data(start=START, count=120)
    strategy = RecordingMomentum(MomentumStrategy(TEST_CONFIG))
    config = _config()
    engine, _ = _engine(config, strategy)
    result = engine.run(START, END, market_data=market_data)

    assert result.signal_start is None
    assert result.equity_curve[0].date == START
    trading_dates = sorted(
        {bar.timestamp.date() for bars in market_data.values() for bar in bars if START <= bar.timestamp.date() <= END}
    )
    expected = _monthly_rebalance_dates(trading_dates, TEST_CONFIG.lookback_days + 1)
    assert date(2024, 1, 2) not in expected
    assert date(2024, 2, 1) in expected
    assert {row.as_of for row in result.rebalance_diagnostics} == expected
    assert result.first_signal_date == date(2024, 2, 1)
    fill_dates = {fill.timestamp.date() for fill in result.fills}
    assert date(2024, 2, 2) in fill_dates
    assert date(2024, 1, 3) not in fill_dates
    years = max((END - START).days, 0) / CALENDAR_DAYS_PER_YEAR
    expected_cagr = (float(result.final_equity / result.initial_capital) ** (1 / years)) - 1
    assert result.annualized_return == pytest.approx(expected_cagr)


@pytest.mark.backtest
def test_insufficient_warmup_does_not_invent_or_peek_future_or_signal_early() -> None:
    lookback_need = LONG_CONFIG.lookback_days + 1
    market_data = _market_data(start=LOOKBACK_252_START, count=80)
    strategy = RecordingMomentum(MomentumStrategy(LONG_CONFIG))
    config = _config(
        start_date=LOOKBACK_252_START,
        end_date=LOOKBACK_252_END,
        warmup_sessions=lookback_need,
        signal_start=LOOKBACK_252_START,
    )
    engine, portfolio = _engine(config, strategy)
    result = engine.run(LOOKBACK_252_START, LOOKBACK_252_END, market_data=market_data)

    assert strategy.seen
    first_as_of, snapshot, signals = strategy.seen[0]
    assert first_as_of == LOOKBACK_252_START
    assert signals == ()
    for symbol, dates in snapshot.items():
        expected = tuple(
            bar.timestamp.date()
            for bar in market_data[symbol]
            if bar.timestamp.date() <= first_as_of
        )
        assert dates == expected
        assert LOOKBACK_252_START - timedelta(days=1) not in dates
        assert all(session <= first_as_of for session in dates)
        assert len(dates) < lookback_need
    assert portfolio.targets[0].positions == ()
    assert any("Insufficient warmup" in warning for warning in result.warnings)
    assert all(fill.timestamp.date() != LOOKBACK_252_START + timedelta(days=1) for fill in result.fills)
    later = [as_of for as_of, _snapshot, later_signals in strategy.seen if later_signals]
    for as_of in later:
        assert as_of > LOOKBACK_252_START


@pytest.mark.backtest
def test_explicit_signal_mode_is_deterministic() -> None:
    market_data = _market_data(start=date(2023, 12, 1), count=160)
    config = _config(signal_start=SIGNAL_START)
    first, _ = _engine(config, MomentumStrategy(TEST_CONFIG))
    second, _ = _engine(config, MomentumStrategy(TEST_CONFIG))
    result_a = first.run(START, END, market_data=deepcopy(market_data))
    result_b = second.run(START, END, market_data=deepcopy(market_data))
    assert result_a.equity_curve == result_b.equity_curve
    assert result_a.fills == result_b.fills
    assert result_a.orders == result_b.orders
    assert result_a.final_equity == result_b.final_equity
    assert result_a.annualized_return == result_b.annualized_return
    assert result_a.first_signal_date == result_b.first_signal_date
    assert result_a.signal_start == SIGNAL_START


@pytest.mark.backtest
def test_future_bars_after_as_of_do_not_enter_explicit_signal_evaluate() -> None:
    market_data = _market_data(start=date(2023, 12, 1), count=160)
    mutated = deepcopy(market_data)
    for symbol, bars in mutated.items():
        bars.append(
            make_series(symbol, 1, start=END + timedelta(days=1), close=Decimal("9"), volume=1)[0]
        )
    strategy = RecordingMomentum(MomentumStrategy(TEST_CONFIG))
    config = _config(signal_start=SIGNAL_START)
    engine, _ = _engine(config, strategy)
    engine.run(START, END, market_data=mutated)
    assert strategy.seen
    for as_of, snapshot, _signals in strategy.seen:
        for dates in snapshot.values():
            assert max(dates) <= as_of
            assert END + timedelta(days=1) not in dates
