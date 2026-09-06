from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine, _bars_as_of, _universe_market_data
from app.broker.simulated import SimulatedBroker
from app.domain.models.market_bar import MarketBar
from app.domain.models.signal import MomentumSignal
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy
from app.strategy.momentum import MomentumStrategy
from tests.fixtures.momentum import TEST_CONFIG, make_bar, make_series

START = date(2024, 1, 2)
END = date(2024, 3, 21)
AS_OF = date(2024, 2, 1)


class RecordingBarStrategy(Strategy):
    """Captures the exact bars the engine passes into evaluate."""

    def __init__(self) -> None:
        self.seen: list[tuple[date, dict[str, tuple[date, ...]]]] = []

    def generate_signals(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> list[MomentumSignal]:
        snapshot = {
            symbol: tuple(bar.timestamp.date() for bar in bars)
            for symbol, bars in market_data.items()
        }
        self.seen.append((as_of, snapshot))
        return []


def _engine(strategy: Strategy, *, warmup_sessions: int = 1) -> BacktestEngine:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=warmup_sessions,
        symbols=("AAA", "BBB"),
    )
    return BacktestEngine(
        strategy=strategy,
        broker=SimulatedBroker(initial_capital=config.initial_capital),
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
    )


def _dates(bars: Sequence[MarketBar]) -> tuple[date, ...]:
    return tuple(bar.timestamp.date() for bar in bars)


@pytest.mark.backtest
def test_bars_as_of_excludes_future_and_keeps_history() -> None:
    bars = make_series("AAA", 10, start=START, close=Decimal("50"))
    as_of = START + timedelta(days=4)
    sliced = _bars_as_of(bars, as_of)
    assert _dates(sliced) == tuple(START + timedelta(days=offset) for offset in range(5))
    assert all(session <= as_of for session in _dates(sliced))
    assert as_of in _dates(sliced)
    assert START in _dates(sliced)


@pytest.mark.backtest
def test_universe_market_data_future_rows_are_physically_absent() -> None:
    market_data = {
        "AAA": make_series("AAA", 60, start=START, close=Decimal("50")),
        "BBB": make_series("BBB", 60, start=START, close=Decimal("50")),
    }
    signal_data, _missing, _eligible, _unusable = _universe_market_data(
        market_data, AS_OF, None, set()
    )
    for symbol, bars in signal_data.items():
        dates = _dates(bars)
        assert dates
        assert max(dates) <= AS_OF
        assert all(session <= AS_OF for session in dates)
        future = [bar for bar in market_data[symbol] if bar.timestamp.date() > AS_OF]
        assert future
        future_ids = {id(bar) for bar in future}
        assert future_ids.isdisjoint({id(bar) for bar in bars})


@pytest.mark.backtest
def test_universe_market_data_max_timestamp_is_at_most_as_of() -> None:
    market_data = {"AAA": make_series("AAA", 60, start=START, close=Decimal("50"))}
    signal_data, *_ = _universe_market_data(market_data, AS_OF, None, set())
    timestamps = [bar.timestamp.date() for bar in signal_data["AAA"]]
    assert max(timestamps) <= AS_OF


@pytest.mark.backtest
def test_first_available_bar_has_no_future_data() -> None:
    bars = make_series("AAA", 8, start=START, close=Decimal("50"))
    sliced = _bars_as_of(bars, START)
    assert _dates(sliced) == (START,)
    assert all(bar.timestamp.date() <= START for bar in sliced)


@pytest.mark.backtest
def test_missing_session_is_not_invented() -> None:
    gap = START + timedelta(days=1)
    bars = [
        make_bar("AAA", START, close=Decimal("50")),
        make_bar("AAA", START + timedelta(days=2), close=Decimal("51")),
        make_bar("AAA", START + timedelta(days=3), close=Decimal("52")),
    ]
    as_of = START + timedelta(days=3)
    sliced = _bars_as_of(bars, as_of)
    dates = _dates(sliced)
    assert gap not in dates
    assert dates == (START, START + timedelta(days=2), START + timedelta(days=3))


@pytest.mark.backtest
def test_as_of_slice_is_independent_per_symbol() -> None:
    market_data = {
        "AAA": make_series("AAA", 40, start=START, close=Decimal("50")),
        "BBB": make_series("BBB", 10, start=date(2024, 2, 15), close=Decimal("50")),
    }
    signal_data, *_ = _universe_market_data(market_data, AS_OF, None, set())
    assert max(_dates(signal_data["AAA"])) <= AS_OF
    assert START in _dates(signal_data["AAA"])
    assert _dates(signal_data["BBB"]) == ()


@pytest.mark.backtest
def test_late_listing_has_no_bars_before_first_quote() -> None:
    first_quote = date(2024, 2, 20)
    market_data = {
        "LATE": make_series("LATE", 20, start=first_quote, close=Decimal("50")),
    }
    before = _universe_market_data(market_data, AS_OF, None, set())[0]
    after = _universe_market_data(market_data, first_quote, None, set())[0]
    assert _dates(before["LATE"]) == ()
    assert min(_dates(after["LATE"])) == first_quote
    assert all(session >= first_quote for session in _dates(after["LATE"]))


@pytest.mark.backtest
def test_lookback_history_through_as_of_is_kept() -> None:
    lookback_start = START
    market_data = {"AAA": make_series("AAA", 60, start=lookback_start, close=Decimal("50"))}
    signal_data, *_ = _universe_market_data(market_data, AS_OF, None, set())
    dates = _dates(signal_data["AAA"])
    expected = tuple(
        bar.timestamp.date() for bar in market_data["AAA"] if bar.timestamp.date() <= AS_OF
    )
    assert dates == expected
    assert lookback_start in dates
    assert AS_OF in dates
    assert len(dates) > 1


@pytest.mark.backtest
def test_engine_evaluate_input_contains_no_bars_after_as_of() -> None:
    market_data = {
        "AAA": make_series("AAA", 80, start=START, close=Decimal("50")),
        "BBB": make_series("BBB", 80, start=START, close=Decimal("50")),
    }
    strategy = RecordingBarStrategy()
    _engine(strategy).run(START, END, market_data=market_data)
    assert strategy.seen
    for as_of, snapshot in strategy.seen:
        for symbol, dates in snapshot.items():
            assert dates, symbol
            assert max(dates) <= as_of
            full = _dates(market_data[symbol])
            assert any(session > as_of for session in full)
            assert all(session <= as_of for session in dates)


@pytest.mark.backtest
def test_same_history_through_t_plus_future_bars_yields_identical_decision() -> None:
    as_of = AS_OF
    history = {
        "NVDA": make_series(
            "NVDA",
            40,
            start=START,
            close=Decimal("50"),
            adjusted_closes=[Decimal("100") + Decimal("2") * Decimal(index) for index in range(40)],
            volume=2_000_000,
        ),
        "MSFT": make_series(
            "MSFT",
            40,
            start=START,
            close=Decimal("50"),
            adjusted_closes=[Decimal("100") + Decimal("1") * Decimal(index) for index in range(40)],
            volume=2_000_000,
        ),
    }
    through_t = {
        symbol: [bar for bar in bars if bar.timestamp.date() <= as_of]
        for symbol, bars in history.items()
    }
    with_future = deepcopy(history)
    for symbol, bars in with_future.items():
        last = bars[-1]
        bars.append(
            make_bar(
                symbol,
                last.timestamp.date() + timedelta(days=1),
                close=Decimal("9"),
                adjusted_close=Decimal("9"),
                volume=1,
            )
        )

    strategy = MomentumStrategy(TEST_CONFIG)
    first = strategy.evaluate(
        _universe_market_data(through_t, as_of, None, set())[0],
        as_of,
    )
    second = strategy.evaluate(
        _universe_market_data(with_future, as_of, None, set())[0],
        as_of,
    )
    assert first.signals == second.signals
    assert first.counts == second.counts
    for bars in _universe_market_data(with_future, as_of, None, set())[0].values():
        assert all(bar.timestamp.date() <= as_of for bar in bars)
        assert all(bar.close != Decimal("9") for bar in bars)
