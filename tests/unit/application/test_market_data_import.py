from datetime import date

import pytest

from app.application.market_data_import import (
    fetch_start_for_import,
    import_market_data_batch,
    resolve_import_symbols,
)
from app.backtest.data import warmup_history_start
from app.data.exceptions import DataImportError, DataProviderError
from app.data.import_summary import MarketDataImportOrigin, MarketDataImportStatus, MarketDataImportSummary
from app.data.interface import MarketDataFetchResult
from app.data.market_data import MarketDataService
from app.universe.factory import HISTORICAL_SP500
from app.universe.service import UniverseService
from tests.fixtures.market_data import InMemoryMarketDataRepository
from tests.fixtures.universe import membership
from tests.unit.data.test_market_data_service import FakeMarketDataProvider
from tests.unit.universe.test_universe_service import FakeRepository


@pytest.mark.unit
def test_resolve_import_symbols_uses_overlapping_window_not_current() -> None:
    repository = FakeRepository()
    repository.rows.extend(
        [
            membership("AAA", date(2010, 1, 1), date(2016, 1, 1)),
            membership("BBB", date(2024, 1, 1), None),
        ]
    )
    service = UniverseService(repository)
    symbols, universe = resolve_import_symbols(
        symbols=None,
        universe=HISTORICAL_SP500,
        start=date(2015, 1, 1),
        end=date(2025, 12, 31),
        universe_service=service,
    )
    assert universe == HISTORICAL_SP500
    assert symbols == ("AAA", "BBB")
    assert service.get_symbols(date(2025, 1, 2)) == ["BBB"]


@pytest.mark.unit
def test_explicit_symbols_win_over_universe() -> None:
    repository = FakeRepository()
    repository.rows.extend([membership("AAA", date(2010, 1, 1), None)])
    service = UniverseService(repository)
    symbols, universe = resolve_import_symbols(
        symbols=["AAPL", "MSFT"],
        universe=HISTORICAL_SP500,
        start=date(2015, 1, 1),
        end=date(2025, 12, 31),
        universe_service=service,
    )
    assert universe == "explicit"
    assert symbols == ("AAPL", "MSFT")


@pytest.mark.unit
def test_fetch_start_extends_warmup_only_for_historical_universe() -> None:
    start = date(2015, 1, 1)
    assert fetch_start_for_import(start, universe=HISTORICAL_SP500, lookback_days=252) == warmup_history_start(
        start, 252
    )
    assert fetch_start_for_import(start, universe="explicit", lookback_days=252) == start


@pytest.mark.unit
def test_resolve_import_requires_symbol_or_universe() -> None:
    with pytest.raises(DataImportError, match="either --symbol or --universe"):
        resolve_import_symbols(symbols=None, universe=None, start=date(2015, 1, 1), end=date(2025, 12, 31))


@pytest.mark.unit
def test_batch_continues_after_provider_failure() -> None:
    def _import(symbol: str) -> MarketDataImportSummary:
        if symbol == "XYZ":
            return MarketDataImportSummary(
                symbol=symbol,
                rows_read=0,
                rows_inserted=0,
                duplicates=0,
                invalid_rows=0,
                start=date(2014, 1, 1),
                end=date(2014, 12, 31),
                status=MarketDataImportStatus.FAILED,
                errors=("provider error",),
                origin=MarketDataImportOrigin.FAILED,
            )
        return MarketDataImportSummary(
            symbol=symbol,
            rows_read=1,
            rows_inserted=1,
            duplicates=0,
            invalid_rows=0,
            start=date(2014, 1, 1),
            end=date(2014, 12, 31),
            status=MarketDataImportStatus.SUCCESS,
            origin=MarketDataImportOrigin.DOWNLOADED,
        )

    report = import_market_data_batch(
        ["AAPL", "XYZ", "MSFT"],
        date(2014, 1, 1),
        date(2014, 12, 31),
        universe="explicit",
        warmup_start=date(2014, 1, 1),
        import_symbol=_import,
    )
    assert report.failed == 1
    assert report.downloaded == 2
    assert [item.symbol for item in report.summaries] == ["AAPL", "XYZ", "MSFT"]
    text = report.format()
    assert "Failed: 1" in text
    assert "XYZ" in text


@pytest.mark.unit
def test_empty_provider_result_is_empty_status() -> None:
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(), rows_read=0, invalid_rows=(), duplicate_timestamps=0)
    )
    service = MarketDataService(provider=provider, repository=InMemoryMarketDataRepository())
    summary = service.import_history(["ZZZ"], date(2024, 1, 1), date(2024, 1, 31))[0]
    assert summary.status == MarketDataImportStatus.EMPTY
    assert summary.origin == MarketDataImportOrigin.EMPTY
    assert summary.rows_inserted == 0


@pytest.mark.unit
def test_provider_failure_is_recorded_without_insert() -> None:
    provider = FakeMarketDataProvider(error=DataProviderError("ticker not found", symbol="XYZ", source="yfinance"))
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)
    summary = service.import_history(["XYZ"], date(2024, 1, 1), date(2024, 1, 31))[0]
    assert summary.status == MarketDataImportStatus.FAILED
    assert summary.origin == MarketDataImportOrigin.FAILED
    assert repository.save_calls == 0
