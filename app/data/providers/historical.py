"""Historical daily OHLCV provider backed by yfinance (injectable for tests)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.data.csv_cache import (
    bars_in_range,
    cache_head_covers,
    cache_path_for_symbol,
    merge_bars,
    read_normalized_csv,
    write_normalized_csv,
)
from app.data.exceptions import DataProviderError
from app.data.interface import MarketDataFetchResult
from app.data.validation import (
    ParsedBar,
    normalize_symbol,
    parsed_bar_to_market_bar,
    sort_and_deduplicate,
    validate_historical_parsed_bar,
)
from app.domain.models.market_bar import MarketBar

logger = logging.getLogger(__name__)

UTC = timezone.utc

RawHistoricalRow = Mapping[str, Any]
HistoricalDownloader = Callable[[str, date, date], Sequence[RawHistoricalRow]]


def download_yfinance_daily(symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    """Download daily OHLCV including Adj Close. Inclusive [start, end]."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataProviderError(
            "yfinance is required for the historical provider; install project dependencies",
            symbol=symbol,
            source="yfinance",
        ) from exc

    # yfinance end is exclusive; add one day to include the requested end date.
    fetch_end = end + timedelta(days=1)
    try:
        frame = yf.download(
            symbol,
            start=start.isoformat(),
            end=fetch_end.isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # noqa: BLE001 - surface provider failures uniformly
        raise DataProviderError(
            f"Failed to download historical data: {exc}",
            symbol=symbol,
            source="yfinance",
        ) from exc

    if frame is None or getattr(frame, "empty", True):
        return []

    # Flatten MultiIndex columns from recent yfinance versions.
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame.columns = [str(col[0]).strip() if isinstance(col, tuple) else str(col) for col in frame.columns]

    rows: list[dict[str, Any]] = []
    for index, series in frame.iterrows():
        if hasattr(index, "to_pydatetime"):
            ts = index.to_pydatetime()
        elif isinstance(index, datetime):
            ts = index
        else:
            ts = datetime.fromisoformat(str(index)[:10])
        trade_day = ts.date() if isinstance(ts, datetime) else date.fromisoformat(str(ts)[:10])
        adj = series.get("Adj Close", series.get("AdjClose"))
        rows.append(
            {
                "date": trade_day,
                "open": series.get("Open"),
                "high": series.get("High"),
                "low": series.get("Low"),
                "close": series.get("Close"),
                "adjusted_close": adj,
                "volume": series.get("Volume"),
            }
        )
    return rows


class HistoricalMarketDataProvider:
    """Fetch daily bars from an external historical source and normalize them.

    Does not write to PostgreSQL. Optionally writes a CSV cache under ``cache_dir``.
    Date range convention: inclusive on both ``start`` and ``end``.
    Timestamps are timezone-aware UTC at 14:30 (matching existing CSV samples).
    """

    def __init__(
        self,
        *,
        downloader: HistoricalDownloader | None = None,
        cache_dir: Path | None = None,
        source_name: str = "yfinance",
    ) -> None:
        self._downloader = downloader or download_yfinance_daily
        self._cache_dir = cache_dir
        self._source_name = source_name

    def get_history(self, symbol: str, start: date, end: date) -> Sequence[MarketBar]:
        return self.fetch_history(symbol, start, end).bars

    def fetch_history(self, symbol: str, start: date, end: date) -> MarketDataFetchResult:
        if start > end:
            raise DataProviderError(
                "start must be <= end",
                symbol=symbol,
                source=self._source_name,
            )

        requested_symbol = normalize_symbol(symbol)
        cached = self._read_cache(requested_symbol)
        if cached and cache_head_covers(cached, start):
            in_range = bars_in_range(cached, start, end)
            unique_bars, duplicate_timestamps = sort_and_deduplicate(in_range)
            logger.info(
                "Historical cache reuse symbol=%s bars=%s",
                requested_symbol,
                len(unique_bars),
            )
            return MarketDataFetchResult(
                bars=tuple(unique_bars),
                rows_read=len(unique_bars),
                invalid_rows=(),
                duplicate_timestamps=duplicate_timestamps,
                from_cache=True,
            )

        download_end = end
        if cached:
            first_cached = min(bar.timestamp.date() for bar in cached)
            download_end = min(end, first_cached - timedelta(days=1))

        if download_end < start:
            in_range = bars_in_range(cached, start, end)
            unique_bars, duplicate_timestamps = sort_and_deduplicate(in_range)
            return MarketDataFetchResult(
                bars=tuple(unique_bars),
                rows_read=len(unique_bars),
                invalid_rows=(),
                duplicate_timestamps=duplicate_timestamps,
                from_cache=True,
            )

        parsed = self._download_parsed(requested_symbol, start, download_end)
        merged = merge_bars(cached, parsed.bars)
        if self._cache_dir is not None and merged:
            path = cache_path_for_symbol(self._cache_dir, requested_symbol)
            write_normalized_csv(merged, path)
            logger.info("Wrote CSV cache path=%s rows=%s", path, len(merged))

        in_range = bars_in_range(merged, start, end)
        unique_bars, extra_duplicates = sort_and_deduplicate(in_range)
        return MarketDataFetchResult(
            bars=tuple(unique_bars),
            rows_read=parsed.rows_read + len(bars_in_range(cached, start, end)),
            invalid_rows=parsed.invalid_rows,
            duplicate_timestamps=parsed.duplicate_timestamps + extra_duplicates,
            from_cache=False,
        )

    def _read_cache(self, symbol: str) -> list[MarketBar]:
        if self._cache_dir is None:
            return []
        return read_normalized_csv(cache_path_for_symbol(self._cache_dir, symbol))

    def _download_parsed(self, symbol: str, start: date, end: date) -> MarketDataFetchResult:
        try:
            raw_rows = self._downloader(symbol, start, end)
        except DataProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DataProviderError(
                f"Historical download failed: {exc}",
                symbol=symbol,
                source=self._source_name,
            ) from exc

        bars: list[MarketBar] = []
        invalid_rows: list[str] = []
        rows_read = 0

        for row_number, raw in enumerate(raw_rows, start=1):
            parsed = _parse_raw_row(
                raw,
                symbol=symbol,
                row_number=row_number,
                source=self._source_name,
            )
            if parsed is None:
                invalid_rows.append(f"unparseable row row={row_number} symbol={symbol}")
                rows_read += 1
                continue

            trade_day = parsed.timestamp.date()
            if trade_day < start or trade_day > end:
                continue

            rows_read += 1
            issues = validate_historical_parsed_bar(parsed)
            if issues:
                invalid_rows.append("; ".join(issue.format() for issue in issues))
                continue
            bars.append(parsed_bar_to_market_bar(parsed))

        unique_bars, duplicate_timestamps = sort_and_deduplicate(bars)
        logger.info(
            "Historical fetch completed symbol=%s rows_read=%s bars=%s duplicates=%s invalid_rows=%s",
            symbol,
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
            from_cache=False,
        )


def _parse_raw_row(
    raw: RawHistoricalRow,
    *,
    symbol: str,
    row_number: int,
    source: str,
) -> ParsedBar | None:
    try:
        trade_day = _coerce_date(raw.get("date") or raw.get("timestamp"))
        open_ = _to_decimal(raw.get("open"))
        high = _to_decimal(raw.get("high"))
        low = _to_decimal(raw.get("low"))
        close = _to_decimal(raw.get("close"))
        adj = raw.get("adjusted_close")
        adjusted_close = None if adj is None or adj == "" else _to_decimal(adj)
        volume = _to_volume(raw.get("volume"))
    except (TypeError, ValueError, InvalidOperation):
        return None

    timestamp = datetime.combine(trade_day, time(14, 30), tzinfo=UTC)
    return ParsedBar(
        symbol=symbol,
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        adjusted_close=adjusted_close,
        volume=volume,
        row_number=row_number,
        source=source,
    )


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text[:10])


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        raise ValueError("missing numeric value")
    # pandas / numpy NaN
    try:
        if value != value:  # noqa: PLR0124
            raise ValueError("NaN")
    except TypeError:
        pass
    return Decimal(str(value))


def _to_volume(value: Any) -> int:
    parsed = _to_decimal(value)
    if parsed != parsed.to_integral_value():
        raise ValueError("volume must be integral")
    return int(parsed)
