from datetime import date
from pathlib import Path

import pytest

from app.universe.exceptions import UniverseSourceError
from app.universe.providers.sp500 import (
    SOURCE_NAME,
    SP500HistoricalSource,
    normalize_constituent_symbol,
    snapshots_to_intervals,
)


def _csv(*rows: str) -> bytes:
    return ("date,tickers\n" + "\n".join(rows) + "\n").encode("utf-8")


@pytest.mark.unit
def test_normalize_strips_removal_suffix() -> None:
    assert normalize_constituent_symbol("aal-199702") == "AAL"
    assert normalize_constituent_symbol("AAPL") == "AAPL"
    assert normalize_constituent_symbol("BRK.B") == "BRK.B"


@pytest.mark.unit
def test_snapshots_to_intervals_emits_half_open_periods() -> None:
    snapshots = [
        (date(2015, 1, 1), frozenset({"AAA", "BBB", "CCC"})),
        (date(2020, 1, 1), frozenset({"AAA", "CCC", "DDD"})),
        (date(2025, 1, 1), frozenset({"AAA", "DDD", "EEE"})),
    ]
    intervals = snapshots_to_intervals(snapshots, source=SOURCE_NAME, source_version="test")
    by_symbol = {item.symbol: item for item in intervals if item.end_date is not None}
    open_ended = {item.symbol: item for item in intervals if item.end_date is None}
    assert by_symbol["BBB"].start_date == date(2015, 1, 1)
    assert by_symbol["BBB"].end_date == date(2020, 1, 1)
    assert by_symbol["CCC"].end_date == date(2025, 1, 1)
    assert open_ended["AAA"].start_date == date(2015, 1, 1)
    assert open_ended["DDD"].start_date == date(2020, 1, 1)
    assert open_ended["EEE"].start_date == date(2025, 1, 1)


@pytest.mark.unit
def test_source_parses_csv_and_does_not_merge_reentry() -> None:
    source = SP500HistoricalSource(fetcher=lambda url: b"unused")
    raw = _csv(
        "2010-01-01,\"AAA,BBB\"",
        "2015-06-01,\"AAA\"",
        "2018-03-01,\"AAA,BBB\"",
    )
    snapshots, raw_records = source.parse_snapshots(raw)
    assert raw_records == 3
    intervals = snapshots_to_intervals(snapshots)
    bbb = [item for item in intervals if item.symbol == "BBB"]
    assert len(bbb) == 2
    assert bbb[0].end_date == date(2015, 6, 1)
    assert bbb[1].start_date == date(2018, 3, 1)
    assert bbb[1].end_date is None


@pytest.mark.unit
def test_source_rejects_invalid_schema() -> None:
    source = SP500HistoricalSource(fetcher=lambda url: b"unused")
    with pytest.raises(UniverseSourceError, match="schema is invalid"):
        source.parse_snapshots(b"foo,bar\n1,2\n")


@pytest.mark.unit
def test_source_load_from_file(tmp_path: Path) -> None:
    path = tmp_path / "sp500.csv"
    path.write_bytes(_csv('2015-01-01,"AAA,BBB,CCC"'))
    loaded = SP500HistoricalSource().load(source_file=path)
    assert loaded.raw_records == 1
    assert loaded.source == SOURCE_NAME
    assert len(loaded.source_version) == 64
    assert sorted(item.symbol for item in loaded.memberships) == ["AAA", "BBB", "CCC"]
    assert all(item.end_date is None for item in loaded.memberships)


@pytest.mark.unit
def test_source_caches_download(tmp_path: Path) -> None:
    cache = tmp_path / "cache.csv"
    payload = _csv('2015-01-01,"AAA"')
    calls: list[str] = []

    def fetcher(url: str) -> bytes:
        calls.append(url)
        return payload

    source = SP500HistoricalSource(fetcher=fetcher, cache_path=cache, source_urls=("https://example.test/sp500.csv",))
    loaded = source.load()
    assert calls
    assert cache.read_bytes() == payload
    assert loaded.cache_path == cache
    assert loaded.memberships[0].symbol == "AAA"
