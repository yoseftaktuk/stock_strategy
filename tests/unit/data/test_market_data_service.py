from collections.abc import Sequence
from datetime import date

import pytest

from app.data.exceptions import DataImportError, DataProviderError
from app.data.import_summary import MarketDataImportStatus
from app.data.interface import MarketDataFetchResult
from app.data.market_data import MarketDataService
from app.domain.models.market_bar import MarketBar
from tests.fixtures.market_data import SAMPLE_BAR, SAMPLE_BAR_MSFT, InMemoryMarketDataRepository


class FakeMarketDataProvider:
    def __init__(
        self,
        result: MarketDataFetchResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[str, date, date]] = []

    def get_history(self, symbol: str, start: date, end: date) -> Sequence[MarketBar]:
        return self.fetch_history(symbol, start, end).bars

    def fetch_history(self, symbol: str, start: date, end: date) -> MarketDataFetchResult:
        self.calls.append((symbol, start, end))
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.unit
def test_import_history_uses_provider_and_repository() -> None:
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(SAMPLE_BAR,), rows_read=1, invalid_rows=(), duplicate_timestamps=0)
    )
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summaries = service.import_history(["aapl"], date(2024, 1, 1), date(2024, 1, 31))

    assert provider.calls == [("AAPL", date(2024, 1, 1), date(2024, 1, 31))]
    assert repository.save_calls == 1
    assert summaries[0].status == MarketDataImportStatus.SUCCESS
    assert summaries[0].rows_read == 1
    assert summaries[0].rows_inserted == 1
    assert summaries[0].symbol == "AAPL"


@pytest.mark.unit
def test_import_history_reports_duplicates_and_invalid_rows() -> None:
    duplicate = SAMPLE_BAR
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(
            bars=(SAMPLE_BAR, duplicate),
            rows_read=4,
            invalid_rows=("high must be >= low row=3 symbol=AAPL",),
            duplicate_timestamps=1,
        )
    )
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))[0]

    assert summary.status == MarketDataImportStatus.SUCCESS_WITH_WARNINGS
    assert summary.rows_inserted == 1
    assert summary.duplicates == 2
    assert summary.invalid_rows == 1
    assert summary.warnings


@pytest.mark.unit
def test_second_import_is_idempotent() -> None:
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(SAMPLE_BAR,), rows_read=1, invalid_rows=(), duplicate_timestamps=0)
    )
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    first = service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))[0]
    second = service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))[0]

    assert first.rows_inserted == 1
    assert second.rows_inserted == 0
    assert second.duplicates == 1
    assert second.status == MarketDataImportStatus.SUCCESS


@pytest.mark.unit
def test_import_history_failed_when_provider_errors() -> None:
    provider = FakeMarketDataProvider(error=DataProviderError("CSV file not found", symbol="AAPL", source="data/raw"))
    repository = InMemoryMarketDataRepository()
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))[0]

    assert summary.status == MarketDataImportStatus.FAILED
    assert summary.rows_inserted == 0
    assert repository.save_calls == 0
    assert summary.errors


@pytest.mark.unit
def test_import_history_raises_on_database_error() -> None:
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(SAMPLE_BAR,), rows_read=1, invalid_rows=(), duplicate_timestamps=0)
    )
    repository = InMemoryMarketDataRepository()
    repository.fail_on_save = True
    service = MarketDataService(provider=provider, repository=repository)

    with pytest.raises(DataImportError, match="Database error"):
        service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))


@pytest.mark.unit
def test_import_history_rejects_invalid_request() -> None:
    service = MarketDataService(provider=FakeMarketDataProvider(), repository=InMemoryMarketDataRepository())
    with pytest.raises(DataImportError, match="symbols must not be empty"):
        service.import_history([], date(2024, 1, 1), date(2024, 1, 31))
    with pytest.raises(DataImportError, match="start must be <="):
        service.import_history(["AAPL"], date(2024, 2, 1), date(2024, 1, 1))


@pytest.mark.unit
def test_get_history_reads_from_repository_not_provider() -> None:
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(SAMPLE_BAR,), rows_read=1, invalid_rows=(), duplicate_timestamps=0)
    )
    repository = InMemoryMarketDataRepository()
    repository.saved = [SAMPLE_BAR, SAMPLE_BAR_MSFT]
    service = MarketDataService(provider=provider, repository=repository)

    bars = service.get_history("AAPL", date(2024, 1, 1), date(2024, 1, 31))

    assert bars == [SAMPLE_BAR]
    assert provider.calls == []
    assert service.get_latest_bar("MSFT") == SAMPLE_BAR_MSFT


@pytest.mark.unit
def test_import_skips_provider_when_database_covers_range() -> None:
    repository = InMemoryMarketDataRepository()
    repository.saved = [SAMPLE_BAR]
    provider = FakeMarketDataProvider(
        MarketDataFetchResult(bars=(SAMPLE_BAR,), rows_read=1, invalid_rows=(), duplicate_timestamps=0)
    )
    service = MarketDataService(provider=provider, repository=repository)

    summary = service.import_history(["AAPL"], date(2024, 1, 1), date(2024, 1, 8))[0]

    assert provider.calls == []
    assert summary.origin.value == "database"
    assert summary.rows_inserted == 0
    assert summary.status.value == "SUCCESS"
