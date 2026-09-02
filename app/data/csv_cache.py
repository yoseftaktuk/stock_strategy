"""Write and reuse normalized market bars in CSV cache files."""

from __future__ import annotations

import csv
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.data.validation import sort_and_deduplicate
from app.domain.exceptions import DomainValidationError
from app.domain.models.market_bar import MarketBar

logger = logging.getLogger(__name__)

CSV_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)

CACHE_RANGE_TOLERANCE_DAYS = 10


def write_normalized_csv(bars: Sequence[MarketBar], path: Path) -> Path:
    """Write bars sorted by timestamp ASC using the canonical CSV schema."""
    ordered = sorted(bars, key=lambda bar: (bar.symbol, bar.timestamp))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for bar in ordered:
            adj = "" if bar.adjusted_close is None else format(bar.adjusted_close, "f")
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat(),
                    "open": format(bar.open, "f"),
                    "high": format(bar.high, "f"),
                    "low": format(bar.low, "f"),
                    "close": format(bar.close, "f"),
                    "adjusted_close": adj,
                    "volume": str(bar.volume),
                }
            )
    return path


def cache_path_for_symbol(cache_dir: Path, symbol: str) -> Path:
    return cache_dir / f"{symbol.strip().upper()}.csv"


def read_normalized_csv(path: Path) -> list[MarketBar]:
    """Read a canonical cache file. Missing or unreadable files yield an empty list."""
    if not path.is_file():
        return []
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return []
            bars: list[MarketBar] = []
            for row in reader:
                bar = _row_to_bar(row)
                if bar is not None:
                    bars.append(bar)
    except (OSError, csv.Error) as exc:
        logger.warning("Failed to read CSV cache path=%s error=%s", path, exc)
        return []
    unique, _duplicates = sort_and_deduplicate(bars)
    return unique


def merge_bars(*groups: Sequence[MarketBar]) -> list[MarketBar]:
    """Union bars by (symbol, timestamp). Existing timestamps are kept."""
    combined = [bar for group in groups for bar in group]
    unique, _duplicates = sort_and_deduplicate(combined)
    return unique


def bars_in_range(bars: Sequence[MarketBar], start: date, end: date) -> list[MarketBar]:
    return [bar for bar in bars if start <= bar.timestamp.date() <= end]


def cache_head_covers(bars: Sequence[MarketBar], start: date) -> bool:
    """True when the earliest bar is no later than ``start`` plus the range tolerance."""
    if not bars:
        return False
    first = min(bar.timestamp.date() for bar in bars)
    return first <= start + timedelta(days=CACHE_RANGE_TOLERANCE_DAYS)


def cache_covers_range(bars: Sequence[MarketBar], start: date, end: date) -> bool:
    """True when first/last bars fall within ``CACHE_RANGE_TOLERANCE_DAYS`` of the window."""
    if not bars:
        return False
    first = min(bar.timestamp.date() for bar in bars)
    last = max(bar.timestamp.date() for bar in bars)
    if first > start + timedelta(days=CACHE_RANGE_TOLERANCE_DAYS):
        return False
    if last < end - timedelta(days=CACHE_RANGE_TOLERANCE_DAYS):
        return False
    return True


def _row_to_bar(row: dict[str, str]) -> MarketBar | None:
    try:
        symbol = (row.get("symbol") or "").strip().upper()
        timestamp = _parse_timestamp(row.get("timestamp") or "")
        open_ = Decimal((row.get("open") or "").strip())
        high = Decimal((row.get("high") or "").strip())
        low = Decimal((row.get("low") or "").strip())
        close = Decimal((row.get("close") or "").strip())
        adj_text = (row.get("adjusted_close") or "").strip()
        adjusted_close = None if adj_text == "" else Decimal(adj_text)
        volume = int(Decimal((row.get("volume") or "").strip()))
        return MarketBar(
            symbol=symbol,
            timestamp=timestamp,
            open=open_,
            high=high,
            low=low,
            close=close,
            adjusted_close=adjusted_close,
            volume=volume,
        )
    except (DomainValidationError, InvalidOperation, ValueError, TypeError):
        return None


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed
