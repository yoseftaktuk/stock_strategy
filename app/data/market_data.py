from collections.abc import Sequence
from datetime import date, timedelta
import logging

from app.data.exceptions import DataImportError, DataProviderError, DataValidationError
from app.data.import_summary import MarketDataImportOrigin, MarketDataImportStatus, MarketDataImportSummary
from app.data.interface import MarketDataProvider
from app.data.validation import normalize_symbol, sort_and_deduplicate
from app.database.repositories.interfaces import MarketDataRepository
from app.domain.models.market_bar import MarketBar

logger = logging.getLogger(__name__)

RANGE_TOLERANCE_DAYS = 10


def minimum_expected_bars(start: date, end: date) -> int:
    """Lower bound of US trading sessions for a requested calendar range.

    Long ranges (>= 1 year) require a substantial trading-day count so tiny
    fixture CSVs cannot report SUCCESS. Short windows skip the hard floor so
    unit tests and spot checks remain usable.
    """
    calendar_days = max((end - start).days, 0)
    if calendar_days < 365:
        return 0
    return max(252, int(calendar_days * 0.5))


class MarketDataService:
    def __init__(self, provider: MarketDataProvider, repository: MarketDataRepository) -> None:
        self._provider = provider
        self._repository = repository

    def import_history(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        *,
        strict_range_coverage: bool = True,
    ) -> list[MarketDataImportSummary]:
        if not symbols:
            raise DataImportError("symbols must not be empty")
        if start > end:
            raise DataImportError("start must be <= end")

        return [
            self._import_symbol(symbol, start, end, strict_range_coverage=strict_range_coverage)
            for symbol in symbols
        ]

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[MarketBar]:
        return self._repository.get_bars(normalize_symbol(symbol), start, end)

    def get_latest_bar(self, symbol: str) -> MarketBar | None:
        return self._repository.get_latest_bar(normalize_symbol(symbol))

    def _import_symbol(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        strict_range_coverage: bool,
    ) -> MarketDataImportSummary:
        requested_symbol = normalize_symbol(symbol)
        logger.info("Import started symbol=%s", requested_symbol)

        stored_before = list(self._repository.get_bars(requested_symbol, start, end))
        if stored_before and _bars_cover_range(start, end, stored_before[0].timestamp, stored_before[-1].timestamp):
            logger.info("Import skipped existing database coverage symbol=%s", requested_symbol)
            return MarketDataImportSummary(
                symbol=requested_symbol,
                rows_read=0,
                rows_inserted=0,
                duplicates=len(stored_before),
                invalid_rows=0,
                start=start,
                end=end,
                status=MarketDataImportStatus.SUCCESS,
                first_timestamp=stored_before[0].timestamp,
                last_timestamp=stored_before[-1].timestamp,
                bars_in_database=len(stored_before),
                origin=MarketDataImportOrigin.DATABASE,
            )

        try:
            fetch_result = self._provider.fetch_history(requested_symbol, start, end)
        except (DataProviderError, DataValidationError, NotImplementedError) as exc:
            logger.exception("Import failed symbol=%s", requested_symbol)
            return _failed_summary(requested_symbol, start, end, str(exc))

        logger.info("Rows received=%s", fetch_result.rows_read)
        if fetch_result.invalid_rows:
            for warning in fetch_result.invalid_rows:
                logger.warning("Validation error symbol=%s message=%s", requested_symbol, warning)
        if fetch_result.duplicate_timestamps:
            logger.warning(
                "Duplicates symbol=%s count=%s",
                requested_symbol,
                fetch_result.duplicate_timestamps,
            )

        origin = (
            MarketDataImportOrigin.CACHED if fetch_result.from_cache else MarketDataImportOrigin.DOWNLOADED
        )

        if fetch_result.rows_read == 0 and not fetch_result.bars:
            return MarketDataImportSummary(
                symbol=requested_symbol,
                rows_read=0,
                rows_inserted=0,
                duplicates=0,
                invalid_rows=0,
                start=start,
                end=end,
                status=MarketDataImportStatus.EMPTY,
                errors=("No data returned for requested range",),
                origin=MarketDataImportOrigin.EMPTY,
            )

        unique_bars, extra_duplicates = sort_and_deduplicate(fetch_result.bars)
        duplicates = fetch_result.duplicate_timestamps + extra_duplicates

        if not unique_bars:
            return _failed_summary(
                requested_symbol,
                start,
                end,
                "No valid bars after validation",
                rows_read=fetch_result.rows_read,
                invalid_rows=len(fetch_result.invalid_rows),
                warnings=fetch_result.invalid_rows,
            )

        try:
            inserted = self._repository.save_bars(unique_bars)
        except Exception as exc:
            logger.exception("Database error during import symbol=%s", requested_symbol)
            raise DataImportError(
                "Database error while saving market bars",
                symbol=requested_symbol,
                source="postgresql",
            ) from exc

        db_duplicates = len(unique_bars) - inserted
        duplicates += db_duplicates
        logger.info("Rows inserted=%s", inserted)

        stored = list(self._repository.get_bars(requested_symbol, start, end))
        first_ts = stored[0].timestamp if stored else None
        last_ts = stored[-1].timestamp if stored else None
        coverage = len(stored)

        errors: list[str] = []
        warnings: list[str] = list(fetch_result.invalid_rows)
        min_bars = minimum_expected_bars(start, end) if strict_range_coverage else 0
        if min_bars > 0 and coverage < min_bars:
            errors.append(
                f"Insufficient historical coverage: need at least {min_bars} bars "
                f"for {start.isoformat()}..{end.isoformat()}, found {coverage}"
            )
        if (end - start).days >= 365:
            range_error = _range_coverage_error(start, end, first_ts, last_ts)
            if range_error:
                if strict_range_coverage:
                    errors.append(range_error)
                else:
                    warnings.append(range_error)

        if errors:
            logger.error("Import failed quality gate symbol=%s errors=%s", requested_symbol, errors)
            return MarketDataImportSummary(
                symbol=requested_symbol,
                rows_read=fetch_result.rows_read,
                rows_inserted=inserted,
                duplicates=duplicates,
                invalid_rows=len(fetch_result.invalid_rows),
                start=start,
                end=end,
                status=MarketDataImportStatus.FAILED,
                errors=tuple(errors),
                warnings=tuple(warnings),
                first_timestamp=first_ts,
                last_timestamp=last_ts,
                bars_in_database=coverage,
                origin=origin,
            )

        if warnings:
            status = MarketDataImportStatus.SUCCESS_WITH_WARNINGS
        elif duplicates and inserted == 0:
            status = MarketDataImportStatus.SUCCESS
        elif duplicates:
            status = MarketDataImportStatus.SUCCESS_WITH_WARNINGS
        else:
            status = MarketDataImportStatus.SUCCESS

        logger.info("Import completed symbol=%s status=%s origin=%s", requested_symbol, status.value, origin.value)
        return MarketDataImportSummary(
            symbol=requested_symbol,
            rows_read=fetch_result.rows_read,
            rows_inserted=inserted,
            duplicates=duplicates,
            invalid_rows=len(fetch_result.invalid_rows),
            start=start,
            end=end,
            status=status,
            warnings=tuple(warnings),
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            bars_in_database=coverage,
            origin=origin,
        )


def _bars_cover_range(start: date, end: date, first_ts: object, last_ts: object) -> bool:
    return _range_coverage_error(start, end, first_ts, last_ts) is None


def _range_coverage_error(
    start: date,
    end: date,
    first_ts: object | None,
    last_ts: object | None,
) -> str | None:
    if first_ts is None or last_ts is None:
        return "Requested range not covered: no bars in database after import"
    first_day = first_ts.date()  # type: ignore[attr-defined]
    last_day = last_ts.date()  # type: ignore[attr-defined]
    if first_day > start + timedelta(days=RANGE_TOLERANCE_DAYS):
        return (
            f"Requested range not covered: first bar {first_day.isoformat()} "
            f"is later than start {start.isoformat()}"
        )
    if last_day < end - timedelta(days=RANGE_TOLERANCE_DAYS):
        return (
            f"Requested range not covered: last bar {last_day.isoformat()} "
            f"is earlier than end {end.isoformat()}"
        )
    return None


def _failed_summary(
    symbol: str,
    start: date,
    end: date,
    error: str,
    *,
    rows_read: int = 0,
    invalid_rows: int = 0,
    duplicates: int = 0,
    warnings: tuple[str, ...] = (),
) -> MarketDataImportSummary:
    return MarketDataImportSummary(
        symbol=symbol,
        rows_read=rows_read,
        rows_inserted=0,
        duplicates=duplicates,
        invalid_rows=invalid_rows,
        start=start,
        end=end,
        status=MarketDataImportStatus.FAILED,
        errors=(error,),
        warnings=warnings,
        origin=MarketDataImportOrigin.FAILED,
    )
