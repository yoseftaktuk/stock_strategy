import csv
import logging
from collections.abc import Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.data.exceptions import DataProviderError, DataValidationError
from app.data.interface import MarketDataFetchResult
from app.data.validation import (
    ParsedBar,
    canonicalize_timestamp,
    is_timezone_aware,
    normalize_symbol,
    parsed_bar_to_market_bar,
    sort_and_deduplicate,
    validate_parsed_bar,
)
from app.domain.models.market_bar import MarketBar

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)


class CSVMarketDataProvider:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[MarketBar]:
        return self.fetch_history(symbol, start, end).bars

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> MarketDataFetchResult:
        requested_symbol = normalize_symbol(symbol)
        source = self._resolve_file(requested_symbol)
        start_dt, end_dt = _utc_range_bounds(start, end)

        try:
            rows = _read_csv_rows(source)
        except (OSError, csv.Error) as exc:
            raise DataProviderError(
                f"Failed to read CSV file: {exc}",
                symbol=requested_symbol,
                source=str(source),
            ) from exc

        bars: list[MarketBar] = []
        invalid_rows: list[str] = []
        rows_read = 0

        for row_number, row in rows:
            parsed = _parse_row(
                row,
                row_number=row_number,
                symbol=requested_symbol,
                source=str(source),
            )
            if normalize_symbol(parsed.symbol) != requested_symbol:
                continue
            if not _in_requested_range(parsed, start, end, start_dt, end_dt):
                continue

            rows_read += 1
            issues = validate_parsed_bar(parsed)
            if issues:
                invalid_rows.append("; ".join(issue.format() for issue in issues))
                continue
            bars.append(parsed_bar_to_market_bar(parsed))

        unique_bars, duplicate_timestamps = sort_and_deduplicate(bars)
        logger.info(
            "CSV fetch completed symbol=%s source=%s rows_read=%s bars=%s duplicates=%s invalid_rows=%s",
            requested_symbol,
            source,
            rows_read,
            len(unique_bars),
            duplicate_timestamps,
            len(invalid_rows),
        )
        return MarketDataFetchResult(
            bars=tuple(unique_bars),
            rows_read=rows_read,
            invalid_rows=tuple(invalid_rows),
            duplicate_timestamps=duplicate_timestamps,
        )

    def _resolve_file(self, symbol: str) -> Path:
        if not self._data_dir.exists():
            raise DataProviderError(
                f"CSV data directory does not exist: {self._data_dir}",
                symbol=symbol,
                source=str(self._data_dir),
            )
        if not self._data_dir.is_dir():
            raise DataProviderError(
                f"CSV data path is not a directory: {self._data_dir}",
                symbol=symbol,
                source=str(self._data_dir),
            )

        wanted = {
            f"{symbol}.csv".lower(),
            f"{symbol.lower()}_daily.csv".lower(),
        }
        matches = sorted(
            path
            for path in self._data_dir.iterdir()
            if path.is_file() and path.name.lower() in wanted
        )
        if not matches:
            raise DataProviderError(
                f"CSV file not found for symbol {symbol}",
                symbol=symbol,
                source=str(self._data_dir),
            )
        return matches[0]


def _read_csv_rows(source: Path) -> list[tuple[int, dict[str, str]]]:
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataProviderError(
                "CSV file is missing a header row",
                source=str(source),
            )
        columns = {name.strip() for name in reader.fieldnames if name}
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise DataProviderError(
                f"CSV file is missing required columns: {', '.join(missing)}",
                source=str(source),
            )
        rows: list[tuple[int, dict[str, str]]] = []
        for index, row in enumerate(reader, start=2):
            normalized = {
                (key.strip() if key else key): (value.strip() if isinstance(value, str) else value)
                for key, value in row.items()
            }
            rows.append((index, normalized))
        return rows


def _parse_row(
    row: dict[str, str],
    *,
    row_number: int,
    symbol: str,
    source: str,
) -> ParsedBar:
    timestamp = _parse_timestamp(
        row.get("timestamp", ""),
        row_number=row_number,
        symbol=symbol,
        source=source,
    )
    return ParsedBar(
        symbol=row.get("symbol", ""),
        timestamp=timestamp,
        open=_parse_decimal(row.get("open", ""), "open", row_number, symbol, source),
        high=_parse_decimal(row.get("high", ""), "high", row_number, symbol, source),
        low=_parse_decimal(row.get("low", ""), "low", row_number, symbol, source),
        close=_parse_decimal(row.get("close", ""), "close", row_number, symbol, source),
        adjusted_close=_parse_optional_decimal(
            row.get("adjusted_close", ""),
            "adjusted_close",
            row_number,
            symbol,
            source,
        ),
        volume=_parse_volume(row.get("volume", ""), row_number, symbol, source),
        row_number=row_number,
        source=source,
    )


def _parse_timestamp(
    value: str,
    *,
    row_number: int,
    symbol: str,
    source: str,
) -> datetime:
    text = value.strip()
    if not text:
        raise DataValidationError(
            f"Invalid timestamp format at row {row_number}: empty value",
            symbol=symbol,
            source=source,
        )
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DataValidationError(
            f"Invalid timestamp format at row {row_number}: {value!r}",
            symbol=symbol,
            source=source,
        ) from exc
    if is_timezone_aware(parsed):
        return canonicalize_timestamp(parsed)
    return parsed


def _parse_decimal(
    value: str,
    field: str,
    row_number: int,
    symbol: str,
    source: str,
) -> Decimal:
    text = value.strip()
    if not text:
        raise DataValidationError(
            f"Invalid numeric value for {field} at row {row_number}: empty value",
            symbol=symbol,
            source=source,
        )
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise DataValidationError(
            f"Invalid numeric value for {field} at row {row_number}: {value!r}",
            symbol=symbol,
            source=source,
        ) from exc


def _parse_optional_decimal(
    value: str,
    field: str,
    row_number: int,
    symbol: str,
    source: str,
) -> Decimal | None:
    if value.strip() == "":
        return None
    return _parse_decimal(value, field, row_number, symbol, source)


def _parse_volume(value: str, row_number: int, symbol: str, source: str) -> int:
    parsed = _parse_decimal(value, "volume", row_number, symbol, source)
    if parsed != parsed.to_integral_value():
        raise DataValidationError(
            f"Invalid numeric value for volume at row {row_number}: {value!r}",
            symbol=symbol,
            source=source,
        )
    return int(parsed)


def _utc_range_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
    return start_dt, end_dt


def _in_requested_range(
    parsed: ParsedBar,
    start: date,
    end: date,
    start_dt: datetime,
    end_dt: datetime,
) -> bool:
    if is_timezone_aware(parsed.timestamp):
        return start_dt <= parsed.timestamp <= end_dt
    return start <= parsed.timestamp.date() <= end
