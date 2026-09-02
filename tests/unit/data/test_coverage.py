from datetime import date

import pytest

from app.data.coverage import build_market_data_coverage
from tests.fixtures.momentum import make_series


@pytest.mark.unit
def test_coverage_report_keeps_members_without_prices() -> None:
    symbols = ["AAA", "BBB", "CCC"]
    bars = {
        "AAA": make_series("AAA", 20, start=date(2014, 1, 2)),
        "CCC": make_series("CCC", 3, start=date(2014, 1, 2)),
    }
    report = build_market_data_coverage(
        symbols,
        bars,
        start=date(2014, 1, 1),
        end=date(2014, 12, 31),
        lookback_days=5,
        universe="historical_sp500",
    )
    by_symbol = {row.symbol: row for row in report.symbols}
    assert report.universe_symbols == 3
    assert report.with_prices == 2
    assert report.without_prices == 1
    assert report.insufficient_history == 1
    assert by_symbol["BBB"].in_universe is True
    assert by_symbol["BBB"].row_count == 0
    assert by_symbol["CCC"].in_universe is True
    assert by_symbol["CCC"].row_count == 3
