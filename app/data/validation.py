from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.models.market_bar import MarketBar


@dataclass(frozen=True)
class ParsedBar:
    """Unvalidated market bar parsed from a data source."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: int
    row_number: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    symbol: str | None = None
    timestamp: datetime | None = None
    source: str | None = None
    row_number: int | None = None

    def format(self) -> str:
        parts = [self.message]
        if self.row_number is not None:
            parts.append(f"row={self.row_number}")
        if self.symbol:
            parts.append(f"symbol={self.symbol}")
        if self.timestamp is not None:
            parts.append(f"timestamp={self.timestamp.isoformat()}")
        if self.source:
            parts.append(f"source={self.source}")
        return " ".join(parts)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def canonicalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
        raise ValueError("timestamp must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


def is_timezone_aware(timestamp: datetime) -> bool:
    return timestamp.tzinfo is not None and timestamp.tzinfo.utcoffset(timestamp) is not None


def validate_parsed_bar(bar: ParsedBar) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not normalize_symbol(bar.symbol):
        issues.append(_issue(bar, "symbol must not be empty"))

    if not is_timezone_aware(bar.timestamp):
        issues.append(_issue(bar, "timestamp must be timezone-aware"))

    prices: list[tuple[str, Decimal]] = [
        ("open", bar.open),
        ("high", bar.high),
        ("low", bar.low),
        ("close", bar.close),
    ]
    if bar.adjusted_close is not None:
        prices.append(("adjusted_close", bar.adjusted_close))

    for name, value in prices:
        if value < 0:
            issues.append(_issue(bar, f"{name} must be non-negative"))

    if bar.high < bar.low:
        issues.append(_issue(bar, "high must be >= low"))
    if bar.high < bar.open:
        issues.append(_issue(bar, "high must be >= open"))
    if bar.high < bar.close:
        issues.append(_issue(bar, "high must be >= close"))
    if bar.low > bar.open:
        issues.append(_issue(bar, "low must be <= open"))
    if bar.low > bar.close:
        issues.append(_issue(bar, "low must be <= close"))
    if bar.volume < 0:
        issues.append(_issue(bar, "volume must be non-negative"))
    return issues


def validate_historical_parsed_bar(bar: ParsedBar) -> list[ValidationIssue]:
    """Strict validation for downloaded historical bars.

    Requires adjusted_close and all OHLC prices to be strictly positive.
    """
    issues = validate_parsed_bar(bar)
    if bar.adjusted_close is None:
        issues.append(_issue(bar, "adjusted_close is required"))
    else:
        for name, value in (
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
            ("adjusted_close", bar.adjusted_close),
        ):
            if value <= 0:
                issues.append(_issue(bar, f"{name} must be positive"))
    return issues


def parsed_bar_to_market_bar(bar: ParsedBar) -> MarketBar:
    timestamp = bar.timestamp
    if is_timezone_aware(timestamp):
        timestamp = canonicalize_timestamp(timestamp)
    return MarketBar(
        symbol=normalize_symbol(bar.symbol),
        timestamp=timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        adjusted_close=bar.adjusted_close,
        volume=bar.volume,
    )


def sort_and_deduplicate(bars: Sequence[MarketBar]) -> tuple[list[MarketBar], int]:
    ordered = sorted(bars, key=lambda item: (item.symbol, item.timestamp))
    unique: list[MarketBar] = []
    seen: set[tuple[str, datetime]] = set()
    duplicates = 0
    for bar in ordered:
        key = (bar.symbol, bar.timestamp)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(bar)
    return unique, duplicates


def _issue(bar: ParsedBar, message: str) -> ValidationIssue:
    return ValidationIssue(
        message=message,
        symbol=bar.symbol or None,
        timestamp=bar.timestamp,
        source=bar.source,
        row_number=bar.row_number,
    )
