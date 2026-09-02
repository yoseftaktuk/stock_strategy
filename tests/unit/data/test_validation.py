from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.data.validation import (
    ParsedBar,
    canonicalize_timestamp,
    normalize_symbol,
    parsed_bar_to_market_bar,
    sort_and_deduplicate,
    validate_parsed_bar,
)
from tests.fixtures.market_data import SAMPLE_BAR, UTC


def _parsed(
    *,
    symbol: str = "AAPL",
    timestamp: datetime | None = None,
    open: str = "150.00",
    high: str = "155.00",
    low: str = "149.00",
    close: str = "154.00",
    adjusted_close: str | None = "154.00",
    volume: int = 1_000_000,
) -> ParsedBar:
    return ParsedBar(
        symbol=symbol,
        timestamp=timestamp or datetime(2024, 1, 2, 16, 0, tzinfo=UTC),
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        adjusted_close=None if adjusted_close is None else Decimal(adjusted_close),
        volume=volume,
        row_number=2,
        source="test.csv",
    )


@pytest.mark.unit
def test_validate_parsed_bar_accepts_valid_bar() -> None:
    assert validate_parsed_bar(_parsed()) == []
    bar = parsed_bar_to_market_bar(_parsed())
    assert bar.symbol == SAMPLE_BAR.symbol
    assert bar.close == SAMPLE_BAR.close


@pytest.mark.unit
def test_validate_parsed_bar_rejects_invalid_ohlc() -> None:
    issues = validate_parsed_bar(_parsed(high="140.00"))
    messages = [issue.message for issue in issues]
    assert "high must be >= low" in messages
    assert "high must be >= open" in messages
    assert "high must be >= close" in messages


@pytest.mark.unit
def test_validate_parsed_bar_rejects_negative_volume() -> None:
    issues = validate_parsed_bar(_parsed(volume=-1))
    assert any(issue.message == "volume must be non-negative" for issue in issues)


@pytest.mark.unit
def test_validate_parsed_bar_rejects_empty_symbol() -> None:
    issues = validate_parsed_bar(_parsed(symbol="  "))
    assert any(issue.message == "symbol must not be empty" for issue in issues)


@pytest.mark.unit
def test_validate_parsed_bar_rejects_naive_timestamp() -> None:
    issues = validate_parsed_bar(_parsed(timestamp=datetime(2024, 1, 2, 16, 0)))
    assert any("timezone-aware" in issue.message for issue in issues)


@pytest.mark.unit
def test_validate_parsed_bar_rejects_negative_prices() -> None:
    issues = validate_parsed_bar(_parsed(open="-1.00", high="2.00", low="-3.00", close="1.00"))
    messages = [issue.message for issue in issues]
    assert "open must be non-negative" in messages
    assert "low must be non-negative" in messages


@pytest.mark.unit
def test_validate_parsed_bar_allows_boundary_zeros() -> None:
    parsed = _parsed(open="0", high="0", low="0", close="0", adjusted_close="0", volume=0)
    assert validate_parsed_bar(parsed) == []
    bar = parsed_bar_to_market_bar(parsed)
    assert bar.open == Decimal("0")
    assert bar.volume == 0


@pytest.mark.unit
def test_normalize_symbol_uppercases() -> None:
    assert normalize_symbol(" aapl ") == "AAPL"


@pytest.mark.unit
def test_canonicalize_timestamp_converts_to_utc() -> None:
    eastern = timezone.utc
    timestamp = datetime(2025, 1, 2, 14, 30, tzinfo=eastern)
    assert canonicalize_timestamp(timestamp).tzinfo == timezone.utc


@pytest.mark.unit
def test_sort_and_deduplicate_keeps_first_after_sort() -> None:
    first = parsed_bar_to_market_bar(_parsed(close="243.85", high="249.10", low="241.82", open="248.93"))
    later_day = parsed_bar_to_market_bar(
        _parsed(
            timestamp=datetime(2024, 1, 3, 16, 0, tzinfo=UTC),
            open="244.00",
            high="246.50",
            low="243.10",
            close="245.20",
            adjusted_close="245.20",
        )
    )
    duplicate = parsed_bar_to_market_bar(_parsed(close="154.00"))

    unique, duplicates = sort_and_deduplicate([first, later_day, duplicate])
    assert duplicates == 1
    assert [bar.timestamp for bar in unique] == [first.timestamp, later_day.timestamp]
    assert unique[0].close == first.close
