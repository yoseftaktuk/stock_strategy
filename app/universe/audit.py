"""Point-in-time universe integrity checks.

Reports membership problems from the interval model and optional local price
windows. Does not delete memberships and does not use a ticker blacklist.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.universe.memory import InMemoryUniverseProvider
from app.universe.models import ConstituentMembership
from app.universe.validation import MembershipIssue, MembershipValidationReport, validate_memberships

FIXTURE_SOURCE = "test-fixture"
DEFAULT_PRICE_GAP_DAYS = 365
DEFAULT_EXTREME_FIRST_CLOSE = Decimal("1000")

CLASS_VALID = "a"
CLASS_TICKER_CHANGE = "b"
CLASS_NORMALIZATION = "c"
CLASS_FIXTURE = "d"
CLASS_BAD_MEMBERSHIP = "e"
CLASS_OTHER = "f"

CLASS_LABELS = {
    CLASS_VALID: "valid historical constituent",
    CLASS_TICKER_CHANGE: "ticker-change mapping issue",
    CLASS_NORMALIZATION: "symbol normalization issue",
    CLASS_FIXTURE: "fixture/test contamination",
    CLASS_BAD_MEMBERSHIP: "bad historical membership data",
    CLASS_OTHER: "other",
}


@dataclass(frozen=True)
class PriceWindow:
    """First and last local bar dates for a symbol, when price files exist."""

    symbol: str
    first_date: date
    last_date: date
    first_close: Decimal | None = None


@dataclass(frozen=True)
class RebalanceUniverse:
    as_of: date
    symbols: tuple[str, ...]
    memberships: tuple[ConstituentMembership, ...]
    invalid: tuple[str, ...]
    suspicious: tuple[str, ...]


@dataclass(frozen=True)
class SymbolInvestigation:
    symbol: str
    first_appearance: date | None
    last_appearance: date | None
    intervals: tuple[ConstituentMembership, ...]
    source: str | None
    rebalance_dates: tuple[date, ...]
    price_first: date | None
    price_last: date | None
    classification: str
    classification_label: str
    notes: str


@dataclass(frozen=True)
class UniverseAuditReport:
    memberships: tuple[ConstituentMembership, ...]
    unique_symbols: tuple[str, ...]
    validation: MembershipValidationReport
    fixture_symbols: tuple[str, ...]
    suspicious_symbols: tuple[str, ...]
    late_price_start: tuple[str, ...]
    membership_after_prices: tuple[str, ...]
    extreme_first_price: tuple[str, ...]
    current_only_leakage: tuple[str, ...]
    rebalances: tuple[RebalanceUniverse, ...]
    investigations: tuple[SymbolInvestigation, ...] = field(default_factory=tuple)

    @property
    def invalid_interval_count(self) -> int:
        return len(self.validation.invalid)

    @property
    def duplicate_count(self) -> int:
        return len(self.validation.duplicates)

    @property
    def overlapping_count(self) -> int:
        return len(self.validation.overlapping)


def month_starts(start: date, end: date) -> list[date]:
    """First calendar day of each month overlapping ``[start, end]`` plus ``start``."""
    if start > end:
        return []
    dates: list[date] = []
    year, month = start.year, start.month
    current = date(year, month, 1)
    if current < start:
        current = _add_month(current)
    while current <= end:
        dates.append(current)
        current = _add_month(current)
    if start not in dates:
        dates.insert(0, start)
        dates.sort()
    return dates


def memberships_as_of(
    memberships: Sequence[ConstituentMembership],
    as_of: date,
) -> list[ConstituentMembership]:
    return [item for item in memberships if item.contains(as_of)]


def symbols_as_of(memberships: Sequence[ConstituentMembership], as_of: date) -> list[str]:
    return sorted({item.symbol for item in memberships_as_of(memberships, as_of)})


def current_symbols(memberships: Sequence[ConstituentMembership]) -> list[str]:
    return sorted({item.symbol for item in memberships if item.end_date is None})


def future_members_present(
    selected: Sequence[str] | set[str],
    memberships: Sequence[ConstituentMembership],
    as_of: date,
) -> set[str]:
    """Current (open-ended) members whose start_date is after ``as_of`` but appear in ``selected``.

    Empty for a correct PIT query. Non-empty if today's membership leaked into a
    historical date.
    """
    selected_set = set(selected)
    leaked: set[str] = set()
    for item in memberships:
        if item.end_date is None and item.start_date > as_of and item.symbol in selected_set:
            leaked.add(item.symbol)
    return leaked


def audit_universe(
    memberships: Sequence[ConstituentMembership],
    *,
    rebalance_dates: Sequence[date] | None = None,
    price_windows: Mapping[str, PriceWindow] | None = None,
    investigate_symbols: Sequence[str] | None = None,
    price_gap_days: int = DEFAULT_PRICE_GAP_DAYS,
    extreme_first_close: Decimal = DEFAULT_EXTREME_FIRST_CLOSE,
    start: date | None = None,
    end: date | None = None,
) -> UniverseAuditReport:
    """Validate PIT memberships and optionally walk rebalance dates."""
    ordered = tuple(memberships)
    validation = validate_memberships(ordered)
    invalid_issues = _interval_construction_issues(ordered)
    if invalid_issues:
        validation = MembershipValidationReport(
            valid=validation.valid,
            duplicates=validation.duplicates,
            invalid=tuple(invalid_issues),
            overlapping=validation.overlapping,
        )

    by_symbol: dict[str, list[ConstituentMembership]] = defaultdict(list)
    for item in ordered:
        by_symbol[item.symbol].append(item)
    unique_symbols = tuple(sorted(by_symbol))

    fixture_symbols = tuple(
        sorted(
            symbol
            for symbol, periods in by_symbol.items()
            if any((item.source or "") == FIXTURE_SOURCE for item in periods)
        )
    )

    windows = dict(price_windows or {})
    corpus_first = min((window.first_date for window in windows.values()), default=None)
    corpus_last = max((window.last_date for window in windows.values()), default=None)

    overlapping_symbols = {issue.symbol for issue in validation.overlapping if issue.symbol}
    invalid_symbols = {issue.symbol for issue in validation.invalid if issue.symbol}

    late_price_start: list[str] = []
    membership_after_prices: list[str] = []
    extreme_first_price: list[str] = []
    for symbol, periods in by_symbol.items():
        window = windows.get(symbol)
        earliest_start = min(item.start_date for item in periods)
        latest_end = _latest_end(periods)
        if window is None:
            continue
        if (
            corpus_first is not None
            and earliest_start < window.first_date
            and (window.first_date - corpus_first).days > price_gap_days
        ):
            late_price_start.append(symbol)
        if (
            corpus_last is not None
            and latest_end is not None
            and window.last_date < latest_end
            and (corpus_last - window.last_date).days > price_gap_days
        ):
            membership_after_prices.append(symbol)
        if (
            latest_end is None
            and corpus_last is not None
            and (corpus_last - window.last_date).days > price_gap_days
        ):
            membership_after_prices.append(symbol)
        if window.first_close is not None and window.first_close >= extreme_first_close:
            extreme_first_price.append(symbol)

    late_price_start_t = tuple(sorted(set(late_price_start)))
    membership_after_prices_t = tuple(sorted(set(membership_after_prices)))
    extreme_first_price_t = tuple(sorted(set(extreme_first_price)))

    dates = list(rebalance_dates or ())
    if not dates and start is not None and end is not None:
        dates = month_starts(start, end)

    rebalances: list[RebalanceUniverse] = []
    leakage: set[str] = set()
    for as_of in dates:
        present = memberships_as_of(ordered, as_of)
        symbols = sorted({item.symbol for item in present})
        present_set = set(symbols)
        invalid: list[str] = []
        suspicious: list[str] = []
        leakage.update(future_members_present(present_set, ordered, as_of))
        for item in present:
            if item.end_date is not None and not (item.start_date <= as_of < item.end_date):
                invalid.append(item.symbol)
            if item.symbol in fixture_symbols or item.symbol in late_price_start_t:
                suspicious.append(item.symbol)
            elif item.symbol in overlapping_symbols or item.symbol in invalid_symbols:
                suspicious.append(item.symbol)
            elif item.symbol in extreme_first_price_t:
                suspicious.append(item.symbol)
        rebalances.append(
            RebalanceUniverse(
                as_of=as_of,
                symbols=tuple(symbols),
                memberships=tuple(present),
                invalid=tuple(sorted(set(invalid))),
                suspicious=tuple(sorted(set(suspicious))),
            )
        )

    suspicious_symbols = tuple(
        sorted(
            set(fixture_symbols)
            | set(late_price_start_t)
            | set(membership_after_prices_t)
            | set(extreme_first_price_t)
            | overlapping_symbols
            | invalid_symbols
            | leakage
        )
    )

    investigate = list(investigate_symbols or ())
    for symbol in suspicious_symbols:
        if symbol not in investigate:
            investigate.append(symbol)
    investigations = tuple(
        investigate_symbol(
            symbol,
            ordered,
            rebalance_dates=dates,
            price_windows=windows,
            fixture_symbols=fixture_symbols,
            overlapping_symbols=overlapping_symbols,
            invalid_symbols=invalid_symbols,
            late_price_start=late_price_start_t,
            membership_after_prices=membership_after_prices_t,
            extreme_first_price=extreme_first_price_t,
        )
        for symbol in investigate
    )

    return UniverseAuditReport(
        memberships=ordered,
        unique_symbols=unique_symbols,
        validation=validation,
        fixture_symbols=fixture_symbols,
        suspicious_symbols=suspicious_symbols,
        late_price_start=late_price_start_t,
        membership_after_prices=membership_after_prices_t,
        extreme_first_price=extreme_first_price_t,
        current_only_leakage=tuple(sorted(leakage)),
        rebalances=tuple(rebalances),
        investigations=investigations,
    )


def investigate_symbol(
    symbol: str,
    memberships: Sequence[ConstituentMembership],
    *,
    rebalance_dates: Sequence[date],
    price_windows: Mapping[str, PriceWindow],
    fixture_symbols: Sequence[str] = (),
    overlapping_symbols: set[str] | None = None,
    invalid_symbols: set[str] | None = None,
    late_price_start: Sequence[str] = (),
    membership_after_prices: Sequence[str] = (),
    extreme_first_price: Sequence[str] = (),
) -> SymbolInvestigation:
    name = symbol.strip().upper()
    intervals = tuple(item for item in memberships if item.symbol == name)
    appearances = [as_of for as_of in rebalance_dates if any(item.contains(as_of) for item in intervals)]
    window = price_windows.get(name)
    classification, notes = _classify(
        name,
        intervals,
        fixture_symbols=fixture_symbols,
        overlapping_symbols=overlapping_symbols or set(),
        invalid_symbols=invalid_symbols or set(),
        late_price_start=late_price_start,
        membership_after_prices=membership_after_prices,
        extreme_first_price=extreme_first_price,
        window=window,
    )
    source = next((item.source for item in intervals if item.source), None)
    return SymbolInvestigation(
        symbol=name,
        first_appearance=appearances[0] if appearances else None,
        last_appearance=appearances[-1] if appearances else None,
        intervals=intervals,
        source=source,
        rebalance_dates=tuple(appearances),
        price_first=window.first_date if window else None,
        price_last=window.last_date if window else None,
        classification=classification,
        classification_label=CLASS_LABELS[classification],
        notes=notes,
    )


def pit_provider(memberships: Sequence[ConstituentMembership]) -> InMemoryUniverseProvider:
    return InMemoryUniverseProvider(memberships)


def current_provider(memberships: Sequence[ConstituentMembership]) -> InMemoryUniverseProvider:
    return InMemoryUniverseProvider(memberships, current_only=True)


def load_price_windows_from_csv(price_path: Path) -> dict[str, PriceWindow]:
    """Read first/last bar dates from local OHLCV CSVs. Does not download."""
    windows: dict[str, PriceWindow] = {}
    if not price_path.is_dir():
        return windows
    for path in sorted(price_path.glob("*.csv")):
        if path.stem.lower() == "sp500_historical":
            continue
        window = _price_window_from_csv(path)
        if window is not None:
            windows[window.symbol] = window
    return windows


def _price_window_from_csv(path: Path) -> PriceWindow | None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            header = handle.readline()
            columns = [part.strip().lower() for part in header.split(",")]
            required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
            if not required.issubset(set(columns)):
                return None
            first = handle.readline()
            if not first:
                return None
            last = first
            for line in handle:
                if line.strip():
                    last = line
    except OSError:
        return None
    first_fields = _split_csv_line(first)
    last_fields = _split_csv_line(last)
    if len(first_fields) < 7 or len(last_fields) < 2:
        return None
    try:
        timestamp_index = columns.index("timestamp")
        close_index = columns.index("close")
        symbol_index = columns.index("symbol")
    except ValueError:
        return None
    symbol = first_fields[symbol_index].strip().upper() or path.stem.strip().upper()
    first_date = _parse_bar_date(first_fields[timestamp_index])
    last_date = _parse_bar_date(last_fields[timestamp_index])
    if first_date is None or last_date is None:
        return None
    first_close: Decimal | None
    try:
        first_close = Decimal(first_fields[close_index])
    except Exception:
        first_close = None
    return PriceWindow(
        symbol=symbol,
        first_date=first_date,
        last_date=last_date,
        first_close=first_close,
    )


def _split_csv_line(line: str) -> list[str]:
    return [part.strip() for part in line.strip().split(",")]


def _parse_bar_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _latest_end(periods: Sequence[ConstituentMembership]) -> date | None:
    if any(item.end_date is None for item in periods):
        return None
    ends = [item.end_date for item in periods if item.end_date is not None]
    return max(ends) if ends else None


def _interval_construction_issues(
    memberships: Sequence[ConstituentMembership],
) -> list[MembershipIssue]:
    issues: list[MembershipIssue] = []
    for item in memberships:
        if item.end_date is not None and item.start_date >= item.end_date:
            issues.append(
                MembershipIssue(
                    "impossible date range",
                    symbol=item.symbol,
                    start_date=item.start_date,
                    end_date=item.end_date,
                )
            )
    return issues


def _classify(
    symbol: str,
    intervals: Sequence[ConstituentMembership],
    *,
    fixture_symbols: Sequence[str],
    overlapping_symbols: set[str],
    invalid_symbols: set[str],
    late_price_start: Sequence[str],
    membership_after_prices: Sequence[str],
    extreme_first_price: Sequence[str],
    window: PriceWindow | None,
) -> tuple[str, str]:
    notes: list[str] = []
    if symbol in fixture_symbols:
        return CLASS_FIXTURE, "Membership source is test-fixture."
    if symbol in invalid_symbols or symbol in overlapping_symbols:
        return CLASS_BAD_MEMBERSHIP, "Invalid or overlapping membership intervals."
    if not intervals:
        return CLASS_OTHER, "Symbol has no membership intervals in the loaded universe."
    if "-" in symbol and len(symbol.split("-")[-1]) == 6 and symbol.split("-")[-1].isdigit():
        return CLASS_NORMALIZATION, "Ticker still has a dataset-only -YYYYMM suffix."
    if symbol in late_price_start:
        notes.append(
            "Local prices start well after the earliest membership start relative to the "
            "price corpus; possible ticker recycling or a different issuer under the same ticker."
        )
        return CLASS_OTHER, " ".join(notes)
    if symbol in extreme_first_price:
        close = window.first_close if window is not None else None
        notes.append(
            f"First local close ({close}) is extreme versus typical US common-stock prices; "
            "Yahoo identity may not match the historical constituent."
        )
        return CLASS_OTHER, " ".join(notes)
    if symbol in membership_after_prices:
        notes.append(
            "Membership extends after local prices end while the corpus still has later bars."
        )
        return CLASS_OTHER, " ".join(notes)
    if window is None:
        notes.append("No local price file; membership may still be valid.")
    else:
        notes.append(
            f"Local prices {window.first_date.isoformat()} → {window.last_date.isoformat()}."
        )
    return CLASS_VALID, " ".join(notes) if notes else "Membership intervals are internally consistent."
