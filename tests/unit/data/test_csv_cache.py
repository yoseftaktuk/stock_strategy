from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.csv_cache import (
    bars_in_range,
    cache_covers_range,
    cache_head_covers,
    merge_bars,
    read_normalized_csv,
    write_normalized_csv,
)
from app.domain.models.market_bar import MarketBar
from tests.fixtures.market_data import UTC


def _bar(symbol: str, day: date) -> MarketBar:
    return MarketBar(
        symbol=symbol,
        timestamp=datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        adjusted_close=Decimal("10.5"),
        volume=100,
    )


@pytest.mark.unit
def test_merge_bars_never_drops_older_rows() -> None:
    older = [_bar("AAPL", date(2014, 1, 2)), _bar("AAPL", date(2014, 1, 3))]
    newer = [_bar("AAPL", date(2014, 1, 3)), _bar("AAPL", date(2014, 6, 2))]
    merged = merge_bars(older, newer)
    assert [bar.timestamp.date() for bar in merged] == [
        date(2014, 1, 2),
        date(2014, 1, 3),
        date(2014, 6, 2),
    ]


@pytest.mark.unit
def test_read_write_normalized_csv_roundtrip(tmp_path: Path) -> None:
    bars = [_bar("MSFT", date(2014, 1, 3)), _bar("MSFT", date(2014, 1, 2))]
    path = tmp_path / "MSFT.csv"
    write_normalized_csv(bars, path)
    loaded = read_normalized_csv(path)
    assert [bar.timestamp.date() for bar in loaded] == [date(2014, 1, 2), date(2014, 1, 3)]
    assert loaded[0].symbol == "MSFT"


@pytest.mark.unit
def test_cache_head_and_range_coverage() -> None:
    bars = [_bar("AAPL", date(2014, 1, 2)), _bar("AAPL", date(2025, 12, 31))]
    assert cache_head_covers(bars, date(2014, 1, 1))
    assert cache_covers_range(bars, date(2014, 1, 1), date(2025, 12, 31))
    assert not cache_head_covers(bars, date(2010, 1, 1))
    assert bars_in_range(bars, date(2014, 1, 1), date(2014, 12, 31))[0].timestamp.date() == date(2014, 1, 2)
