"""Join historical universe membership with local market-data availability."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.data.import_summary import MarketDataImportOrigin, MarketDataImportSummary
from app.data.market_data import RANGE_TOLERANCE_DAYS
from app.domain.models.market_bar import MarketBar


@dataclass(frozen=True)
class SymbolCoverage:
    symbol: str
    in_universe: bool
    first_date: date | None
    last_date: date | None
    row_count: int
    missing_adjusted_close: int
    validation_errors: tuple[str, ...]
    download_status: str


@dataclass(frozen=True)
class MarketDataCoverageReport:
    universe: str
    start: date
    end: date
    warmup_start: date | None
    symbols: tuple[SymbolCoverage, ...]
    universe_symbols: int
    with_prices: int
    without_prices: int
    incomplete_range: int
    insufficient_history: int
    lookback_days: int

    def format(self) -> str:
        lines = [
            "Historical Market Data Coverage",
            f"Universe: {self.universe or 'explicit'}",
            f"Requested: {self.start.isoformat()} → {self.end.isoformat()}",
        ]
        if self.warmup_start is not None:
            lines.append(f"Warm-up start: {self.warmup_start.isoformat()}")
        lines.extend(
            [
                f"Historical Universe Symbols: {self.universe_symbols}",
                f"Market Data Available: {self.with_prices}",
                f"Missing Market Data: {self.without_prices}",
                f"Incomplete Range: {self.incomplete_range}",
                f"Insufficient History: {self.insufficient_history}",
            ]
        )
        return "\n".join(lines)


def build_market_data_coverage(
    symbols: Sequence[str],
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    *,
    start: date,
    end: date,
    lookback_days: int,
    universe: str = "",
    warmup_start: date | None = None,
    import_summaries: Mapping[str, MarketDataImportSummary] | None = None,
) -> MarketDataCoverageReport:
    """Build per-symbol coverage. Membership is the input symbol list, not prices."""
    need = lookback_days + 1
    rows: list[SymbolCoverage] = []
    with_prices = 0
    without_prices = 0
    incomplete_range = 0
    insufficient_history = 0
    summaries = import_summaries or {}

    for symbol in symbols:
        bars = list(bars_by_symbol.get(symbol, ()))
        first = bars[0].timestamp.date() if bars else None
        last = bars[-1].timestamp.date() if bars else None
        missing_adj = sum(1 for bar in bars if bar.adjusted_close is None)
        summary = summaries.get(symbol)
        validation_errors = summary.errors if summary is not None else ()
        status = _download_status(summary, has_bars=bool(bars))
        if bars:
            with_prices += 1
            if _incomplete_range(first, last, start, end):
                incomplete_range += 1
            if len(bars) < need:
                insufficient_history += 1
        else:
            without_prices += 1
        rows.append(
            SymbolCoverage(
                symbol=symbol,
                in_universe=True,
                first_date=first,
                last_date=last,
                row_count=len(bars),
                missing_adjusted_close=missing_adj,
                validation_errors=validation_errors,
                download_status=status,
            )
        )

    return MarketDataCoverageReport(
        universe=universe,
        start=start,
        end=end,
        warmup_start=warmup_start,
        symbols=tuple(rows),
        universe_symbols=len(symbols),
        with_prices=with_prices,
        without_prices=without_prices,
        incomplete_range=incomplete_range,
        insufficient_history=insufficient_history,
        lookback_days=lookback_days,
    )


def _incomplete_range(
    first: date | None,
    last: date | None,
    start: date,
    end: date,
) -> bool:
    if first is None or last is None:
        return True
    if first > start + timedelta(days=RANGE_TOLERANCE_DAYS):
        return True
    if last < end - timedelta(days=RANGE_TOLERANCE_DAYS):
        return True
    return False


def _download_status(summary: MarketDataImportSummary | None, *, has_bars: bool) -> str:
    if summary is not None:
        if summary.origin == MarketDataImportOrigin.FAILED:
            return "failed"
        return summary.origin.value
    return "available" if has_bars else "missing"
