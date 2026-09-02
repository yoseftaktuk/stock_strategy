from datetime import date
from decimal import Decimal

import pytest

from app.strategy.filters import LiquidityFilter, MomentumFilter, PriceFilter
from tests.fixtures.momentum import make_bar, make_series


@pytest.mark.unit
def test_price_filter_rejects_below_threshold() -> None:
    result = PriceFilter(Decimal("10")).is_eligible(
        [make_bar("AAPL", date(2024, 1, 2), close=Decimal("9.99"))]
    )
    assert result.passed is False


@pytest.mark.unit
def test_price_filter_accepts_exact_threshold() -> None:
    result = PriceFilter(Decimal("10")).is_eligible(
        [make_bar("AAPL", date(2024, 1, 2), close=Decimal("10.00"))]
    )
    assert result.passed is True


@pytest.mark.unit
def test_price_filter_accepts_above_threshold() -> None:
    result = PriceFilter(Decimal("10")).is_eligible(
        [make_bar("AAPL", date(2024, 1, 2), close=Decimal("10.01"))]
    )
    assert result.passed is True


@pytest.mark.unit
def test_price_filter_uses_latest_close() -> None:
    bars = make_series(
        "AAPL",
        count=2,
        closes=[Decimal("9.99"), Decimal("10.00")],
    )
    assert PriceFilter(Decimal("10")).is_eligible(bars).passed is True


@pytest.mark.unit
def test_liquidity_filter_rejects_below_threshold() -> None:
    bars = [make_bar("AAPL", date(2024, 1, 2), close=Decimal("1"), volume=19_999_999)]
    result = LiquidityFilter(1, Decimal("20000000")).is_eligible(bars)
    assert result.passed is False


@pytest.mark.unit
def test_liquidity_filter_accepts_exact_threshold() -> None:
    bars = [make_bar("AAPL", date(2024, 1, 2), close=Decimal("1"), volume=20_000_000)]
    result = LiquidityFilter(1, Decimal("20000000")).is_eligible(bars)
    assert result.passed is True


@pytest.mark.unit
def test_liquidity_filter_accepts_above_threshold() -> None:
    bars = [make_bar("AAPL", date(2024, 1, 2), close=Decimal("1"), volume=20_000_001)]
    result = LiquidityFilter(1, Decimal("20000000")).is_eligible(bars)
    assert result.passed is True


@pytest.mark.unit
def test_liquidity_filter_uses_twenty_day_mean() -> None:
    bars = make_series("AAPL", count=20, close=Decimal("10"), volume=2_000_000)
    result = LiquidityFilter(20, Decimal("20000000")).is_eligible(bars)
    assert result.passed is True

    poor = make_series("AAPL", count=20, close=Decimal("10"), volume=1_999_999)
    assert LiquidityFilter(20, Decimal("20000000")).is_eligible(poor).passed is False


@pytest.mark.unit
def test_liquidity_filter_rejects_insufficient_window() -> None:
    bars = make_series("AAPL", count=19, close=Decimal("10"), volume=2_000_000)
    result = LiquidityFilter(20, Decimal("20000000")).is_eligible(bars)
    assert result.passed is False


@pytest.mark.unit
def test_momentum_filter_rejects_negative() -> None:
    assert MomentumFilter().is_eligible(Decimal("-0.10")).passed is False


@pytest.mark.unit
def test_momentum_filter_rejects_zero() -> None:
    assert MomentumFilter().is_eligible(Decimal("0")).passed is False


@pytest.mark.unit
def test_momentum_filter_accepts_positive() -> None:
    assert MomentumFilter().is_eligible(Decimal("0.01")).passed is True
