from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.strategy.config import MomentumConfig
from app.strategy.momentum import MomentumStrategy
from tests.fixtures.momentum import (
    TEST_CONFIG,
    history_as_of,
    make_bar,
    make_momentum_series,
    make_series,
    universe_market_data,
)


def _strategy(config: MomentumConfig | None = None) -> MomentumStrategy:
    return MomentumStrategy(config or TEST_CONFIG)


@pytest.mark.unit
def test_strategy_ranks_universe() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    signals = _strategy().generate_signals(universe_market_data(), as_of)
    assert [signal.symbol for signal in signals] == ["NVDA", "PLTR", "MSFT", "AAPL", "AMD"]
    assert [signal.rank for signal in signals] == [1, 2, 3, 4, 5]
    assert signals[0].momentum == Decimal("0.80")
    assert signals[1].momentum == Decimal("0.74")
    assert signals[2].momentum == Decimal("0.50")
    assert signals[3].momentum == Decimal("0.20")
    assert signals[4].momentum == Decimal("0.10")
    assert all(signal.eligible for signal in signals)
    assert all(signal.date == as_of for signal in signals)


@pytest.mark.unit
def test_insufficient_history_yields_no_signal() -> None:
    as_of = date(2024, 1, 4)
    signals = _strategy().generate_signals({"AAPL": make_series("AAPL", count=3)}, as_of)
    assert signals == []


@pytest.mark.unit
def test_skip_period_is_not_used() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    strategy = _strategy()
    first = strategy.generate_signals({"AAPL": bars}, as_of)

    mutated = list(bars)
    last = mutated[-1]
    mutated[-1] = make_bar(
        last.symbol,
        last.timestamp.date(),
        close=last.close,
        adjusted_close=Decimal("999"),
        volume=last.volume,
    )
    second = strategy.generate_signals({"AAPL": mutated}, as_of)
    assert first == second
    assert first[0].momentum == Decimal("0.20")


@pytest.mark.unit
def test_look_ahead_bias_future_bars_do_not_change_signal() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data(extra_future_bars=3)
    strategy = _strategy()
    first = strategy.generate_signals(market_data, as_of)

    mutated: dict[str, list] = {}
    for symbol, bars in market_data.items():
        updated = list(bars)
        for index in range(-3, 0):
            bar = updated[index]
            updated[index] = make_bar(
                bar.symbol,
                bar.timestamp.date(),
                close=Decimal("9"),
                adjusted_close=Decimal("9"),
                volume=1,
            )
        mutated[symbol] = updated

    second = strategy.generate_signals(mutated, as_of)
    assert first == second
    assert [signal.symbol for signal in first] == ["NVDA", "PLTR", "MSFT", "AAPL", "AMD"]


@pytest.mark.unit
def test_top_n_truncates_to_three() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = {
        f"S{index:02d}": make_momentum_series(
            f"S{index:02d}",
            lookback_days=5,
            skip_days=1,
            lookback_price=Decimal("100"),
            skip_price=Decimal(str(200 - index * 10)),
        )
        for index in range(10)
    }
    config = MomentumConfig(
        lookback_days=5,
        skip_days=1,
        top_n=3,
        min_price=Decimal("10"),
        liquidity_window_days=2,
        min_dollar_volume=Decimal("1000"),
    )
    signals = _strategy(config).generate_signals(market_data, as_of)
    assert len(signals) == 3
    assert [signal.symbol for signal in signals] == ["S00", "S01", "S02"]
    assert [signal.rank for signal in signals] == [1, 2, 3]


@pytest.mark.unit
def test_top_n_does_not_pad_when_fewer_qualify() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = {
        symbol: bars
        for symbol, bars in universe_market_data().items()
        if symbol in {"NVDA", "MSFT", "AAPL", "AMD"}
    }
    signals = _strategy().generate_signals(market_data, as_of)
    assert len(signals) == 4
    assert [signal.symbol for signal in signals] == ["NVDA", "MSFT", "AAPL", "AMD"]


@pytest.mark.unit
def test_negative_momentum_is_excluded_before_ranking() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    market_data["LOSS"] = make_momentum_series(
        "LOSS",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("80"),
    )
    signals = _strategy().generate_signals(market_data, as_of)
    assert "LOSS" not in [signal.symbol for signal in signals]
    assert [signal.rank for signal in signals] == [1, 2, 3, 4, 5]


@pytest.mark.unit
def test_price_filter_applied_before_ranking() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    cheap = make_momentum_series(
        "CHEAP",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("200"),
        close=Decimal("9.99"),
    )
    market_data = universe_market_data()
    market_data["CHEAP"] = cheap
    signals = _strategy().generate_signals(market_data, as_of)
    assert "CHEAP" not in [signal.symbol for signal in signals]


@pytest.mark.unit
def test_malformed_symbol_does_not_abort_strategy() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    lookback_bar = market_data["MSFT"][0]
    market_data["MSFT"] = list(market_data["MSFT"])
    market_data["MSFT"][0] = make_bar(
        lookback_bar.symbol,
        lookback_bar.timestamp.date(),
        close=lookback_bar.close,
        volume=lookback_bar.volume,
        missing_adjusted_close=True,
    )
    market_data["BAD"] = []  # type: ignore[assignment]
    signals = _strategy().generate_signals(market_data, as_of)
    symbols = [signal.symbol for signal in signals]
    assert "MSFT" not in symbols
    assert "BAD" not in symbols
    assert symbols == ["NVDA", "PLTR", "AAPL", "AMD"]


@pytest.mark.unit
def test_unexpected_malformed_payload_is_skipped() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    market_data["BAD_DATA"] = [object()]  # type: ignore[list-item]
    signals = _strategy().generate_signals(market_data, as_of)
    assert "BAD_DATA" not in [signal.symbol for signal in signals]
    assert [signal.symbol for signal in signals] == ["NVDA", "PLTR", "MSFT", "AAPL", "AMD"]


@pytest.mark.unit
def test_determinism() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    strategy = _strategy()
    first = strategy.generate_signals(market_data, as_of)
    second = strategy.generate_signals(market_data, as_of)
    third = _strategy().generate_signals(market_data, as_of)
    assert first == second == third


@pytest.mark.unit
def test_does_not_mutate_input_lists() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    for bars in market_data.values():
        bars.reverse()
    snapshot = {symbol: list(bars) for symbol, bars in market_data.items()}
    identities = {symbol: [id(bar) for bar in bars] for symbol, bars in market_data.items()}

    signals = _strategy().generate_signals(market_data, as_of)

    assert signals
    for symbol, bars in market_data.items():
        assert bars == snapshot[symbol]
        assert [id(bar) for bar in bars] == identities[symbol]


@pytest.mark.unit
def test_tie_break_by_symbol_in_strategy() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = {
        "MSFT": make_momentum_series(
            "MSFT",
            lookback_days=5,
            skip_days=1,
            lookback_price=Decimal("100"),
            skip_price=Decimal("150"),
        ),
        "AAPL": make_momentum_series(
            "AAPL",
            lookback_days=5,
            skip_days=1,
            lookback_price=Decimal("100"),
            skip_price=Decimal("150"),
        ),
    }
    signals = _strategy().generate_signals(market_data, as_of)
    assert [signal.symbol for signal in signals] == ["AAPL", "MSFT"]
    assert [signal.rank for signal in signals] == [1, 2]


@pytest.mark.unit
def test_as_of_on_weekend_uses_last_available_session() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days) + timedelta(days=1)
    signals = _strategy().generate_signals(universe_market_data(), as_of)
    assert [signal.symbol for signal in signals] == ["NVDA", "PLTR", "MSFT", "AAPL", "AMD"]
    assert all(signal.date == as_of for signal in signals)


@pytest.mark.unit
def test_deepcopy_of_inputs_is_unnecessary_for_safety() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    original = universe_market_data()
    clone = deepcopy(original)
    _strategy().generate_signals(original, as_of)
    assert original.keys() == clone.keys()
    for symbol in original:
        assert original[symbol] == clone[symbol]
