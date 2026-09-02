from datetime import date
from pathlib import Path

import pytest

from app.universe.audit import (
    CLASS_OTHER,
    CLASS_VALID,
    audit_universe,
    load_price_windows_from_csv,
)
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource

CACHE = Path(DEFAULT_CACHE_PATH)
PRICE_DIR = Path("data/raw")


@pytest.mark.unit
def test_cached_universe_classifies_xyz_tko_se_har() -> None:
    if not CACHE.is_file():
        pytest.skip(f"membership cache missing: {CACHE}")
    loaded = SP500HistoricalSource(fetcher=lambda url: b"unused").load(source_file=CACHE)
    windows = load_price_windows_from_csv(PRICE_DIR)
    report = audit_universe(
        loaded.memberships,
        price_windows=windows,
        investigate_symbols=["XYZ", "TKO", "SE", "HAR"],
    )
    by_symbol = {item.symbol: item for item in report.investigations}

    xyz = by_symbol["XYZ"]
    assert xyz.classification == CLASS_VALID
    assert xyz.intervals
    assert all(item.start_date >= date(2025, 1, 1) for item in xyz.intervals)

    tko = by_symbol["TKO"]
    assert tko.classification == CLASS_VALID
    assert tko.intervals
    assert all(item.start_date >= date(2025, 1, 1) for item in tko.intervals)

    se = by_symbol["SE"]
    assert se.classification == CLASS_OTHER
    assert se.intervals
    assert se.price_first is not None
    assert se.intervals[0].end_date is not None
    assert se.price_first >= se.intervals[0].end_date

    har = by_symbol["HAR"]
    assert har.classification == CLASS_OTHER
    assert "HAR" in report.extreme_first_price
    assert har.price_first is not None
    har_end = har.intervals[0].end_date
    assert har_end is not None
    assert har.intervals[0].start_date < har.price_first < har_end
