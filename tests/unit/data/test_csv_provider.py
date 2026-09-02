from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.exceptions import DataProviderError, DataValidationError
from app.data.providers.csv import CSVMarketDataProvider
from app.data.providers.ibkr import IBKRMarketDataProvider

UTC = timezone.utc
TEST_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.mark.unit
def test_csv_provider_reads_valid_file() -> None:
    provider = CSVMarketDataProvider(TEST_DATA_DIR)
    bars = provider.get_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))

    assert [bar.symbol for bar in bars] == ["AAPL", "AAPL", "AAPL"]
    assert [bar.timestamp for bar in bars] == [
        datetime(2025, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2025, 1, 3, 14, 30, tzinfo=UTC),
        datetime(2025, 1, 6, 14, 30, tzinfo=UTC),
    ]
    assert bars[0].close == Decimal("243.85")
    assert bars[0].adjusted_close == Decimal("243.85")
    assert bars[0].volume == 55_740_700


@pytest.mark.unit
def test_csv_provider_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "AAPL.csv"
    csv_path.write_text("symbol,timestamp,open,close\nAAPL,2025-01-02T14:30:00+00:00,1,2\n", encoding="utf-8")
    provider = CSVMarketDataProvider(tmp_path)

    with pytest.raises(DataProviderError, match="missing required columns"):
        provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.unit
def test_csv_provider_invalid_timestamp_is_fatal(tmp_path: Path) -> None:
    _write_aapl_csv(tmp_path, "AAPL,not-a-timestamp,248.93,249.10,241.82,243.85,243.85,100")
    provider = CSVMarketDataProvider(tmp_path)

    with pytest.raises(DataValidationError, match="Invalid timestamp format"):
        provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.unit
def test_csv_provider_naive_timestamp_is_row_level_invalid(tmp_path: Path) -> None:
    _write_aapl_csv(tmp_path, "AAPL,2025-01-02T14:30:00,248.93,249.10,241.82,243.85,243.85,100")
    provider = CSVMarketDataProvider(tmp_path)

    result = provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    assert result.bars == ()
    assert result.rows_read == 1
    assert result.invalid_rows
    assert "timezone-aware" in result.invalid_rows[0]


@pytest.mark.unit
def test_csv_provider_invalid_numeric_is_fatal(tmp_path: Path) -> None:
    _write_aapl_csv(tmp_path, "AAPL,2025-01-02T14:30:00+00:00,not-a-number,249.10,241.82,243.85,243.85,100")
    provider = CSVMarketDataProvider(tmp_path)

    with pytest.raises(DataValidationError, match="Invalid numeric value"):
        provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.unit
def test_csv_provider_invalid_ohlc_and_negative_volume(tmp_path: Path) -> None:
    source = TEST_DATA_DIR / "invalid_market_data.csv"
    (tmp_path / "AAPL.csv").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    provider = CSVMarketDataProvider(tmp_path)

    result = provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    assert len(result.bars) == 1
    assert result.rows_read == 3
    assert len(result.invalid_rows) == 2
    assert any("high must be >=" in message for message in result.invalid_rows)
    assert any("volume must be non-negative" in message for message in result.invalid_rows)


@pytest.mark.unit
def test_csv_provider_duplicate_timestamps(tmp_path: Path) -> None:
    source = TEST_DATA_DIR / "duplicate_market_data.csv"
    (tmp_path / "AAPL.csv").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    provider = CSVMarketDataProvider(tmp_path)

    result = provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    assert len(result.bars) == 2
    assert result.duplicate_timestamps == 1
    assert result.bars[0].timestamp < result.bars[1].timestamp
    assert result.bars[0].close == Decimal("243.85")


@pytest.mark.unit
def test_csv_provider_sorts_chronologically(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "AAPL.csv",
        [
            "AAPL,2025-01-06T14:30:00+00:00,245.50,248.00,244.80,247.15,247.15,100",
            "AAPL,2025-01-02T14:30:00+00:00,248.93,249.10,241.82,243.85,243.85,100",
            "AAPL,2025-01-03T14:30:00+00:00,244.00,246.50,243.10,245.20,245.20,100",
        ],
    )
    provider = CSVMarketDataProvider(tmp_path)
    bars = provider.get_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    assert [bar.timestamp.date() for bar in bars] == [
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 6),
    ]


@pytest.mark.unit
def test_csv_provider_date_filtering() -> None:
    provider = CSVMarketDataProvider(TEST_DATA_DIR)
    bars = provider.get_history("AAPL", date(2025, 1, 3), date(2025, 1, 3))
    assert len(bars) == 1
    assert bars[0].timestamp.date() == date(2025, 1, 3)


@pytest.mark.unit
def test_csv_provider_resolves_daily_filename() -> None:
    provider = CSVMarketDataProvider(TEST_DATA_DIR)
    bars = provider.get_history("MSFT", date(2025, 1, 1), date(2025, 1, 31))
    assert len(bars) == 3
    assert bars[0].symbol == "MSFT"


@pytest.mark.unit
def test_csv_provider_missing_file(tmp_path: Path) -> None:
    provider = CSVMarketDataProvider(tmp_path)
    with pytest.raises(DataProviderError, match="CSV file not found"):
        provider.get_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.unit
def test_ibkr_provider_remains_unimplemented() -> None:
    provider = IBKRMarketDataProvider()
    with pytest.raises(NotImplementedError, match="IBKR market data"):
        provider.get_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))
    with pytest.raises(NotImplementedError, match="IBKR market data"):
        provider.fetch_history("AAPL", date(2025, 1, 1), date(2025, 1, 31))


def _write_aapl_csv(directory: Path, row: str) -> None:
    _write_csv(directory / "AAPL.csv", [row])


def _write_csv(path: Path, rows: list[str]) -> None:
    header = "symbol,timestamp,open,high,low,close,adjusted_close,volume"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
