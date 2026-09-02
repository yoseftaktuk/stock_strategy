"""Ticker-interval validation.

Invalid and overlapping intervals for the same (scheme, ticker) must not be persisted.
Adjacent half-open intervals are allowed. Distinct securities may share a ticker
on disjoint intervals (recycling).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.domain.models.security import SecurityTicker


@dataclass(frozen=True)
class TickerIssue:
    message: str
    scheme: str | None = None
    ticker: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    def format(self) -> str:
        parts = [self.message]
        if self.scheme:
            parts.append(f"scheme={self.scheme}")
        if self.ticker:
            parts.append(f"ticker={self.ticker}")
        if self.valid_from is not None:
            parts.append(f"from={self.valid_from.isoformat()}")
        if self.valid_to is not None:
            parts.append(f"to={self.valid_to.isoformat()}")
        return " ".join(parts)


@dataclass(frozen=True)
class TickerValidationReport:
    valid: tuple[SecurityTicker, ...]
    duplicates: tuple[SecurityTicker, ...]
    overlapping: tuple[TickerIssue, ...] = field(default_factory=tuple)

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.overlapping)


def _interval_key(ticker: SecurityTicker) -> tuple[str, str, date, date | None]:
    return (ticker.scheme, ticker.ticker, ticker.valid_from, ticker.valid_to)


def _effective_end(ticker: SecurityTicker) -> date:
    return ticker.valid_to if ticker.valid_to is not None else date.max


def intervals_overlap(left: SecurityTicker, right: SecurityTicker) -> bool:
    """Half-open overlap: adjacent intervals that share a boundary do not overlap."""
    if left.scheme != right.scheme or left.ticker != right.ticker:
        return False
    return left.valid_from < _effective_end(right) and right.valid_from < _effective_end(left)


def validate_tickers(tickers: Sequence[SecurityTicker]) -> TickerValidationReport:
    """Detect exact duplicates and per-(scheme, ticker) overlapping intervals."""
    duplicates: list[SecurityTicker] = []
    unique: list[SecurityTicker] = []
    seen: set[tuple[str, str, date, date | None]] = set()
    for ticker in tickers:
        key = _interval_key(ticker)
        if key in seen:
            duplicates.append(ticker)
            continue
        seen.add(key)
        unique.append(ticker)

    overlapping: list[TickerIssue] = []
    by_key: dict[tuple[str, str], list[SecurityTicker]] = defaultdict(list)
    for ticker in unique:
        by_key[(ticker.scheme, ticker.ticker)].append(ticker)

    for (scheme, symbol), periods in by_key.items():
        ordered = sorted(periods, key=lambda item: (item.valid_from, _effective_end(item)))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if intervals_overlap(current, other):
                    overlapping.append(
                        TickerIssue(
                            "overlapping ticker intervals",
                            scheme=scheme,
                            ticker=symbol,
                            valid_from=current.valid_from,
                            valid_to=current.valid_to,
                        )
                    )
                    overlapping.append(
                        TickerIssue(
                            "overlapping ticker intervals",
                            scheme=scheme,
                            ticker=symbol,
                            valid_from=other.valid_from,
                            valid_to=other.valid_to,
                        )
                    )

    return TickerValidationReport(
        valid=tuple(unique),
        duplicates=tuple(duplicates),
        overlapping=tuple(overlapping),
    )
