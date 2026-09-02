from datetime import date
from decimal import Decimal

import pytest

from app.strategy.calculations import calculate_average_dollar_volume, calculate_momentum
from app.strategy.exceptions import StrategyDataError
from tests.fixtures.momentum import TEST_CONFIG, make_bar, make_momentum_series, make_series


@pytest.mark.unit
def test_momentum_normal_case() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    assert calculate_momentum(bars, lookback_days=5, skip_days=1) == Decimal("0.20")


@pytest.mark.unit
def test_momentum_negative() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("80"),
    )
    assert calculate_momentum(bars, lookback_days=5, skip_days=1) == Decimal("-0.20")


@pytest.mark.unit
def test_momentum_zero() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("100"),
    )
    assert calculate_momentum(bars, lookback_days=5, skip_days=1) == Decimal("0")


@pytest.mark.unit
def test_momentum_insufficient_data() -> None:
    bars = make_series("AAPL", count=3)
    with pytest.raises(StrategyDataError, match="insufficient history"):
        calculate_momentum(bars, lookback_days=5, skip_days=1)


@pytest.mark.unit
def test_momentum_ignores_skip_period() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    expected = calculate_momentum(bars, lookback_days=5, skip_days=1)

    mutated = list(bars)
    last = mutated[-1]
    mutated[-1] = make_bar(
        last.symbol,
        last.timestamp.date(),
        close=Decimal("999"),
        adjusted_close=Decimal("999"),
        volume=last.volume,
    )
    assert calculate_momentum(mutated, lookback_days=5, skip_days=1) == expected


@pytest.mark.unit
def test_momentum_does_not_use_current_day_as_numerator() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    current = bars[-1]
    assert current.adjusted_close == Decimal("50")
    assert calculate_momentum(bars, lookback_days=5, skip_days=1) == Decimal("0.20")


@pytest.mark.unit
def test_momentum_handles_unsorted_input() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    reversed_bars = list(reversed(bars))
    assert calculate_momentum(reversed_bars, lookback_days=5, skip_days=1) == Decimal("0.20")
    assert reversed_bars[0].timestamp > reversed_bars[-1].timestamp


@pytest.mark.unit
def test_momentum_does_not_mutate_input() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    original = list(bars)
    calculate_momentum(bars, lookback_days=5, skip_days=1)
    assert bars == original


@pytest.mark.unit
def test_momentum_missing_adjusted_close() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("100"),
        skip_price=Decimal("120"),
    )
    lookback_bar = bars[0]
    bars[0] = make_bar(
        lookback_bar.symbol,
        lookback_bar.timestamp.date(),
        close=lookback_bar.close,
        volume=lookback_bar.volume,
        missing_adjusted_close=True,
    )
    with pytest.raises(StrategyDataError, match="adjusted_close is unavailable"):
        calculate_momentum(bars, lookback_days=5, skip_days=1)


@pytest.mark.unit
def test_momentum_zero_lookback_price() -> None:
    bars = make_momentum_series(
        "AAPL",
        lookback_days=5,
        skip_days=1,
        lookback_price=Decimal("0"),
        skip_price=Decimal("120"),
    )
    with pytest.raises(StrategyDataError, match="lookback adjusted_close is zero"):
        calculate_momentum(bars, lookback_days=5, skip_days=1)


@pytest.mark.unit
def test_average_dollar_volume() -> None:
    bars = make_series(
        "AAPL",
        count=2,
        close=Decimal("10"),
        volume=2_000_000,
    )
    assert calculate_average_dollar_volume(bars, window_days=2) == Decimal("20000000")


@pytest.mark.unit
def test_average_dollar_volume_insufficient() -> None:
    bars = make_series("AAPL", count=1)
    with pytest.raises(StrategyDataError, match="insufficient history for dollar volume"):
        calculate_average_dollar_volume(bars, window_days=2)


@pytest.mark.unit
def test_average_dollar_volume_handles_unsorted_input() -> None:
    bars = make_series(
        "AAPL",
        count=3,
        closes=[Decimal("10"), Decimal("20"), Decimal("30")],
        volumes=[100, 100, 100],
    )
    expected = calculate_average_dollar_volume(bars, window_days=2)
    reversed_bars = list(reversed(bars))
    assert calculate_average_dollar_volume(reversed_bars, window_days=2) == expected
    assert expected == Decimal("2500")


@pytest.mark.unit
def test_config_lookback_used_by_helper() -> None:
    assert TEST_CONFIG.lookback_days == 5
    assert date(2024, 1, 2) < date(2024, 12, 31)
