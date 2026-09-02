"""Orchestrate market-data import for explicit symbols or the historical PIT universe."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
import logging
import time

from app.backtest.data import warmup_history_start
from app.data.exceptions import DataImportError
from app.data.import_summary import MarketDataImportOrigin, MarketDataImportStatus, MarketDataImportSummary
from app.data.market_data import MarketDataService
from app.data.validation import normalize_symbol
from app.universe.factory import HISTORICAL_SP500
from app.universe.service import UniverseService

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_DELAY_SECONDS = 0.15


@dataclass(frozen=True)
class MarketDataBatchImportReport:
    universe: str
    start: date
    end: date
    warmup_start: date
    symbols: tuple[str, ...]
    summaries: tuple[MarketDataImportSummary, ...] = field(default_factory=tuple)

    @property
    def downloaded(self) -> int:
        return sum(1 for item in self.summaries if item.origin == MarketDataImportOrigin.DOWNLOADED)

    @property
    def cached(self) -> int:
        return sum(1 for item in self.summaries if item.origin == MarketDataImportOrigin.CACHED)

    @property
    def already_in_database(self) -> int:
        return sum(1 for item in self.summaries if item.origin == MarketDataImportOrigin.DATABASE)

    @property
    def failed(self) -> int:
        return sum(1 for item in self.summaries if item.status == MarketDataImportStatus.FAILED)

    @property
    def empty(self) -> int:
        return sum(1 for item in self.summaries if item.status == MarketDataImportStatus.EMPTY)

    @property
    def rows_inserted(self) -> int:
        return sum(item.rows_inserted for item in self.summaries)

    @property
    def duplicates_skipped(self) -> int:
        return sum(item.duplicates for item in self.summaries)

    def format(self) -> str:
        lines = [
            "Historical Market Data Import",
            f"Universe: {self.universe}",
            f"Requested: {self.start.isoformat()} → {self.end.isoformat()}",
            f"Warm-up start: {self.warmup_start.isoformat()}",
            f"Historical Universe Symbols: {len(self.symbols)}",
            f"Successfully Downloaded: {self.downloaded}",
            f"Already Cached: {self.cached}",
            f"Already in Database: {self.already_in_database}",
            f"Failed: {self.failed}",
            f"Empty: {self.empty}",
            f"Rows Inserted: {self.rows_inserted}",
            f"Duplicate Rows Skipped: {self.duplicates_skipped}",
        ]
        failed_rows = [item for item in self.summaries if item.status == MarketDataImportStatus.FAILED]
        empty_rows = [item for item in self.summaries if item.status == MarketDataImportStatus.EMPTY]
        if failed_rows:
            lines.append("Failed symbols:")
            lines.extend(f"  - {item.symbol}: {item.errors[0] if item.errors else 'failed'}" for item in failed_rows)
        if empty_rows:
            lines.append("Empty symbols:")
            lines.extend(f"  - {item.symbol}" for item in empty_rows)
        return "\n".join(lines)


def resolve_import_symbols(
    *,
    symbols: Sequence[str] | None,
    universe: str | None,
    start: date,
    end: date,
    universe_service: UniverseService | None = None,
) -> tuple[tuple[str, ...], str]:
    """Return (symbols, universe_label). Explicit symbols win over a named universe."""
    explicit = tuple(normalize_symbol(symbol) for symbol in symbols or () if symbol.strip())
    if explicit:
        return explicit, "explicit"
    kind = (universe or "").strip().lower()
    if kind == HISTORICAL_SP500:
        if universe_service is None:
            raise DataImportError("universe service is required for historical_sp500 import")
        discovered = tuple(universe_service.symbols_overlapping_window(start, end))
        if not discovered:
            raise DataImportError("historical_sp500 universe has no members overlapping the requested window")
        return discovered, HISTORICAL_SP500
    raise DataImportError("either --symbol or --universe historical_sp500 is required")


def fetch_start_for_import(
    start: date,
    *,
    universe: str,
    lookback_days: int,
) -> date:
    if universe == HISTORICAL_SP500:
        return warmup_history_start(start, lookback_days)
    return start


def import_market_data_batch(
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    universe: str,
    warmup_start: date,
    import_symbol: Callable[[str], MarketDataImportSummary],
    request_delay_seconds: float = 0.0,
) -> MarketDataBatchImportReport:
    """Import each symbol via ``import_symbol``. Provider/empty failures do not abort the batch."""
    summaries: list[MarketDataImportSummary] = []
    total = len(symbols)
    for index, symbol in enumerate(symbols):
        logger.info("Importing symbol=%s (%s/%s)", symbol, index + 1, total)
        try:
            summary = import_symbol(symbol)
        except DataImportError as exc:
            logger.exception("Database error during import symbol=%s", symbol)
            summary = MarketDataImportSummary(
                symbol=symbol,
                rows_read=0,
                rows_inserted=0,
                duplicates=0,
                invalid_rows=0,
                start=start,
                end=end,
                status=MarketDataImportStatus.FAILED,
                errors=(str(exc),),
                origin=MarketDataImportOrigin.FAILED,
            )
        summaries.append(summary)
        if (
            request_delay_seconds > 0
            and index + 1 < total
            and summary.origin == MarketDataImportOrigin.DOWNLOADED
        ):
            time.sleep(request_delay_seconds)
    return MarketDataBatchImportReport(
        universe=universe,
        start=start,
        end=end,
        warmup_start=warmup_start,
        symbols=tuple(symbols),
        summaries=tuple(summaries),
    )


def import_one_with_service(
    service: MarketDataService,
    symbol: str,
    start: date,
    end: date,
    *,
    strict_range_coverage: bool,
) -> MarketDataImportSummary:
    return service.import_history(
        [symbol],
        start,
        end,
        strict_range_coverage=strict_range_coverage,
    )[0]
