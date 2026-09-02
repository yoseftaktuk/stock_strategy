from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.csv_cache import write_normalized_csv
from app.data.import_summary import MarketDataImportStatus
from app.data.market_data import MarketDataService, minimum_expected_bars
from app.data.providers.historical import HistoricalMarketDataProvider
from app.data.quality_report import inspect_market_bars
from app.domain.models.market_bar import MarketBar
from tests.fixtures.market_data import InMemoryMarketDataRepository, UTC


def _raw(
    day: date,
    *,
    open_: str = "10.00",
    high: str = "11.00",
    low: str = "9.50",
    close: str = "10.50",
    adj: str | None = "10.40",
    volume: int = 1_000,
) -> dict[str, object]:
    return {
        "date": day,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "adjusted_close": adj,
        "volume": volume,
    }


@pytest.mark.unit
def test_historical_provider_returns_market_bars() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 3))]

    def downloader(symbol: str, start: date, end: date) -> list[dict[str, object]]:
        assert symbol == "AAPL"
        return rows

    provider = HistoricalMarketDataProvider(downloader=downloader)
    result = provider.fetch_history("AAPL", date(2014, 1, 1), date(2014, 1, 31))

    assert result.rows_read == 2
    assert len(result.bars) == 2
    assert result.bars[0].symbol == "AAPL"
    assert result.bars[0].adjusted_close == Decimal("10.40")
    assert result.bars[0].timestamp == datetime(2014, 1, 2, 14, 30, tzinfo=UTC)


@pytest.mark.unit
def test_historical_provider_respects_date_range() -> None:
    rows = [
        _raw(date(2013, 12, 31)),
        _raw(date(2014, 1, 2)),
        _raw(date(2014, 1, 15)),
        _raw(date(2015, 1, 2)),
    ]

    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    result = provider.fetch_history("MSFT", date(2014, 1, 1), date(2014, 12, 31))

    assert [bar.timestamp.date() for bar in result.bars] == [date(2014, 1, 2), date(2014, 1, 15)]
    assert result.rows_read == 2


@pytest.mark.unit
def test_historical_provider_normalizes_data() -> None:
    provider = HistoricalMarketDataProvider(
        downloader=lambda *_: [_raw(date(2014, 1, 2), open_="10", high="11", low="9", close="10.5", adj="10.1")]
    )
    bar = provider.get_history("aapl", date(2014, 1, 1), date(2014, 1, 31))[0]

    assert bar.symbol == "AAPL"
    assert bar.timestamp.tzinfo is not None
    assert bar.open == Decimal("10")
    assert bar.close == Decimal("10.5")
    assert bar.adjusted_close == Decimal("10.1")


@pytest.mark.unit
def test_invalid_ohlc_row_is_rejected() -> None:
    rows = [_raw(date(2014, 1, 2), high="8.00", low="9.00", open_="9.50", close="9.25")]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    result = provider.fetch_history("AAPL", date(2014, 1, 1), date(2014, 1, 31))

    assert result.bars == ()
    assert result.rows_read == 1
    assert result.invalid_rows
    assert "high must be >=" in result.invalid_rows[0] or "high must be" in result.invalid_rows[0]


@pytest.mark.unit
def test_missing_adjusted_close_is_rejected() -> None:
    rows = [_raw(date(2014, 1, 2), adj=None)]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    result = provider.fetch_history("AAPL", date(2014, 1, 1), date(2014, 1, 31))

    assert result.bars == ()
    assert any("adjusted_close is required" in warning for warning in result.invalid_rows)


@pytest.mark.unit
def test_duplicate_rows_are_removed() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 2)), _raw(date(2014, 1, 3))]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    result = provider.fetch_history("AAPL", date(2014, 1, 1), date(2014, 1, 31))

    assert len(result.bars) == 2
    assert result.duplicate_timestamps == 1


@pytest.mark.unit
def test_csv_cache_is_created(tmp_path: Path) -> None:
    provider = HistoricalMarketDataProvider(
        downloader=lambda *_: [_raw(date(2014, 1, 3)), _raw(date(2014, 1, 2))],
        cache_dir=tmp_path,
    )
    provider.fetch_history("AAPL", date(2014, 1, 1), date(2014, 1, 31))

    cache = tmp_path / "AAPL.csv"
    assert cache.exists()
    text = cache.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "symbol,timestamp,open,high,low,close,adjusted_close,volume"
    assert "AAPL,2014-01-02T14:30:00+00:00" in text


@pytest.mark.unit
def test_csv_cache_is_sorted(tmp_path: Path) -> None:
    bars = [
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2014, 1, 3, 14, 30, tzinfo=UTC),
            open=Decimal("11"),
            high=Decimal("12"),
            low=Decimal("10"),
            close=Decimal("11.5"),
            adjusted_close=Decimal("11.5"),
            volume=100,
        ),
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2014, 1, 2, 14, 30, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10.5"),
            adjusted_close=Decimal("10.5"),
            volume=100,
        ),
    ]
    path = tmp_path / "AAPL.csv"
    write_normalized_csv(bars, path)
    lines = path.read_text(encoding="utf-8").splitlines()[1:]
    assert lines[0].startswith("AAPL,2014-01-02")
    assert lines[1].startswith("AAPL,2014-01-03")


@pytest.mark.unit
def test_second_import_creates_zero_new_rows() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 3))]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    first = service.import_history(["AAPL"], date(2014, 1, 1), date(2014, 1, 31))[0]
    second = service.import_history(["AAPL"], date(2014, 1, 1), date(2014, 1, 31))[0]

    assert first.rows_inserted == 2
    assert second.rows_inserted == 0
    assert second.duplicates == 2
    assert second.status == MarketDataImportStatus.SUCCESS


@pytest.mark.unit
def test_import_reports_correct_summary() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 3), high="8", low="9")]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(["AAPL"], date(2014, 1, 1), date(2014, 1, 31))[0]

    assert summary.rows_read == 2
    assert summary.rows_inserted == 1
    assert summary.invalid_rows == 1
    assert summary.status == MarketDataImportStatus.SUCCESS_WITH_WARNINGS
    assert summary.first_timestamp is not None
    assert summary.bars_in_database == 1


@pytest.mark.unit
def test_universe_mode_persists_short_series_as_warning() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 3)), _raw(date(2014, 1, 6))]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(
        ["XYZ"],
        date(2014, 1, 1),
        date(2025, 12, 31),
        strict_range_coverage=False,
    )[0]

    assert summary.status == MarketDataImportStatus.SUCCESS_WITH_WARNINGS
    assert summary.rows_inserted == 3
    assert summary.bars_in_database == 3
    assert any("Requested range not covered" in warning for warning in summary.warnings)


@pytest.mark.unit
def test_tiny_dataset_does_not_report_success_for_long_range() -> None:
    rows = [_raw(date(2014, 1, 2)), _raw(date(2014, 1, 3)), _raw(date(2014, 1, 6))]
    provider = HistoricalMarketDataProvider(downloader=lambda *_: rows)
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(["AAPL"], date(2014, 1, 1), date(2025, 12, 31))[0]

    assert minimum_expected_bars(date(2014, 1, 1), date(2025, 12, 31)) >= 2000
    assert summary.status == MarketDataImportStatus.FAILED
    assert any("Insufficient historical coverage" in error for error in summary.errors)


@pytest.mark.unit
def test_csv_cache_is_reused_without_download(tmp_path: Path) -> None:
    calls: list[tuple[str, date, date]] = []

    def downloader(symbol: str, start: date, end: date) -> list[dict[str, object]]:
        calls.append((symbol, start, end))
        raise AssertionError("downloader should not be called when cache covers the window")

    first = HistoricalMarketDataProvider(
        downloader=lambda *_: [_raw(date(2014, 1, 2)), _raw(date(2014, 12, 31))],
        cache_dir=tmp_path,
    )
    first.fetch_history("AAPL", date(2014, 1, 1), date(2014, 12, 31))

    second = HistoricalMarketDataProvider(downloader=downloader, cache_dir=tmp_path)
    result = second.fetch_history("AAPL", date(2014, 1, 1), date(2014, 12, 31))
    assert calls == []
    assert result.from_cache is True
    assert len(result.bars) == 2


@pytest.mark.unit
def test_short_tail_cache_is_reused_without_download(tmp_path: Path) -> None:
    HistoricalMarketDataProvider(
        downloader=lambda *_: [_raw(date(2014, 1, 2)), _raw(date(2018, 6, 1))],
        cache_dir=tmp_path,
    ).fetch_history("XYZ", date(2014, 1, 1), date(2018, 6, 30))

    calls: list[tuple[str, date, date]] = []

    def downloader(symbol: str, start: date, end: date) -> list[dict[str, object]]:
        calls.append((symbol, start, end))
        return []

    result = HistoricalMarketDataProvider(downloader=downloader, cache_dir=tmp_path).fetch_history(
        "XYZ", date(2014, 1, 1), date(2025, 12, 31)
    )
    assert calls == []
    assert result.from_cache is True
    assert result.bars[-1].timestamp.date() == date(2018, 6, 1)


@pytest.mark.unit
def test_missing_cache_head_downloads_prefix_and_merges(tmp_path: Path) -> None:
    HistoricalMarketDataProvider(
        downloader=lambda *_: [_raw(date(2015, 1, 5)), _raw(date(2015, 6, 1))],
        cache_dir=tmp_path,
    ).fetch_history("AAPL", date(2015, 1, 1), date(2015, 6, 30))

    calls: list[tuple[str, date, date]] = []

    def downloader(symbol: str, start: date, end: date) -> list[dict[str, object]]:
        calls.append((symbol, start, end))
        return [_raw(date(2014, 6, 2))]

    result = HistoricalMarketDataProvider(downloader=downloader, cache_dir=tmp_path).fetch_history(
        "AAPL", date(2014, 6, 1), date(2015, 6, 30)
    )
    assert calls == [("AAPL", date(2014, 6, 1), date(2015, 1, 4))]
    assert result.from_cache is False
    assert [bar.timestamp.date() for bar in result.bars][0] == date(2014, 6, 2)
    cached = (tmp_path / "AAPL.csv").read_text(encoding="utf-8")
    assert "2014-06-02" in cached
    assert "2015-06-01" in cached


@pytest.mark.unit
def test_quality_report_counts_symbols_and_gaps() -> None:
    bars = [
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2014, 1, 2, 14, 30, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            adjusted_close=Decimal("10"),
            volume=100,
        ),
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2014, 1, 15, 14, 30, tzinfo=UTC),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            adjusted_close=None,
            volume=0,
        ),
    ]
    report = inspect_market_bars(bars)
    assert report.symbol_count == 1
    assert report.total_bars == 2
    assert report.missing_adjusted_close_count == 1
    assert report.non_positive_volume_count == 1
    assert report.suspicious_gaps
