"""Point-in-time market-data coverage versus Security Master identity.

PIT membership, identity resolution, market-data existence, and market-data
validity are four separate states. Callers must not delete memberships or use
a ticker blacklist. Coverage is measured against the membership interval
clipped to the research window, not against "CSV file exists".
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.data.price_quality import DEFAULT_EXTREME_FIRST_CLOSE
from app.data.validation import normalize_symbol
from app.domain.models.security import RESOLUTION_RESOLVED, RESOLUTION_UNRESOLVED, STATUS_DELISTED
from app.security_master.interface import SecurityMaster
from app.security_master.vendor import preferred_vendor_symbol, vendor_fetch_symbols
from app.universe.audit import PriceWindow, month_starts
from app.universe.models import ConstituentMembership

REASON_A_UNAVAILABLE = "A_unavailable"
REASON_B_TICKER_CHANGE = "B_ticker_change"
REASON_C_TICKER_RECYCLED = "C_ticker_recycled"
REASON_D_UNRESOLVED_IDENTITY = "D_unresolved_identity"
REASON_E_VENDOR_SYMBOL_DIFFERS = "E_vendor_symbol_differs"
REASON_F_DELISTED = "F_delisted"
REASON_G_DATA_UNDER_OTHER_TICKER = "G_data_under_other_ticker"
REASON_H_IDENTITY_VALIDATION_FAILED = "H_identity_validation_failed"
REASON_I_INSUFFICIENT_EVIDENCE = "I_insufficient_evidence"

MARKET_MISSING = "missing"
MARKET_AVAILABLE = "available"
MARKET_AVAILABLE_OTHER = "available_other_ticker"
MARKET_PARTIAL = "partial"
MARKET_UNUSABLE = "unusable"

QUALITY_VALID = "valid"
QUALITY_UNUSABLE = "unusable"
QUALITY_NA = "not_applicable"
QUALITY_PARTIAL = "partial"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

REBALANCE_ENCOUNTER_START = date(2016, 1, 1)
DEFAULT_WINDOW_START = date(2015, 1, 1)
DEFAULT_WINDOW_END = date(2025, 12, 31)

COVERAGE_CSV_FIELDS = (
    "security_id",
    "seed_key",
    "historical_ticker",
    "pit_start",
    "pit_end",
    "pit_intervals",
    "identity_status",
    "market_data_status",
    "vendor_symbol",
    "price_start",
    "price_end",
    "coverage_days",
    "expected_days",
    "coverage_ratio",
    "quality_status",
    "reason",
    "confidence",
    "rebalance_encountered",
    "local_listing_csv",
    "notes",
)


@dataclass(frozen=True)
class PitCoverageRow:
    security_id: int | None
    seed_key: str | None
    historical_ticker: str
    pit_start: date
    pit_end: date | None
    pit_intervals: str
    identity_status: str
    market_data_status: str
    vendor_symbol: str
    price_start: date | None
    price_end: date | None
    coverage_days: int
    expected_days: int
    coverage_ratio: float
    quality_status: str
    reason: str
    confidence: str
    rebalance_encountered: bool
    local_listing_csv: bool
    notes: str

    def as_csv_dict(self) -> dict[str, str]:
        return {
            "security_id": "" if self.security_id is None else str(self.security_id),
            "seed_key": self.seed_key or "",
            "historical_ticker": self.historical_ticker,
            "pit_start": self.pit_start.isoformat(),
            "pit_end": "" if self.pit_end is None else self.pit_end.isoformat(),
            "pit_intervals": self.pit_intervals,
            "identity_status": self.identity_status,
            "market_data_status": self.market_data_status,
            "vendor_symbol": self.vendor_symbol,
            "price_start": "" if self.price_start is None else self.price_start.isoformat(),
            "price_end": "" if self.price_end is None else self.price_end.isoformat(),
            "coverage_days": str(self.coverage_days),
            "expected_days": str(self.expected_days),
            "coverage_ratio": f"{self.coverage_ratio:.4f}",
            "quality_status": self.quality_status,
            "reason": self.reason,
            "confidence": self.confidence,
            "rebalance_encountered": "true" if self.rebalance_encountered else "false",
            "local_listing_csv": "true" if self.local_listing_csv else "false",
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PitCoverageReport:
    start: date
    end: date
    universe_source: str
    pit_securities: int
    rebalance_encountered: int
    valid_data: int
    missing: int
    partial: int
    unusable: int
    unresolved_identity: int
    rebalance_missing: int
    window_missing_listing_csv: int
    rows: tuple[PitCoverageRow, ...]

    def missing_rows(self) -> tuple[PitCoverageRow, ...]:
        return tuple(row for row in self.rows if not row.local_listing_csv)

    def format(self) -> str:
        lines = [
            "Historical Market Data Coverage Audit",
            f"Window: {self.start.isoformat()} → {self.end.isoformat()}",
            f"Universe source: {self.universe_source}",
            f"PIT securities overlapping window: {self.pit_securities}",
            f"Rebalance-encountered (from {REBALANCE_ENCOUNTER_START.isoformat()}): {self.rebalance_encountered}",
            f"Valid data (PIT-interval coverage > 0, usable): {self.valid_data}",
            f"Missing (no valid PIT-interval prices): {self.missing}",
            f"Partial (0 < coverage_ratio < 1): {self.partial}",
            f"Unusable: {self.unusable}",
            f"Unresolved identity: {self.unresolved_identity}",
            f"Listing CSV absent (window): {self.window_missing_listing_csv}",
            f"Listing CSV absent (rebalance-encountered): {self.rebalance_missing}",
        ]
        return "\n".join(lines)


def build_pit_coverage(
    memberships: Sequence[ConstituentMembership],
    price_windows: Mapping[str, PriceWindow],
    master: SecurityMaster | None,
    *,
    start: date = DEFAULT_WINDOW_START,
    end: date = DEFAULT_WINDOW_END,
    universe_source: str = "",
    extreme_first_close: Decimal = DEFAULT_EXTREME_FIRST_CLOSE,
) -> PitCoverageReport:
    """Join PIT membership, Security Master, and local price windows."""
    by_symbol: dict[str, list[ConstituentMembership]] = defaultdict(list)
    for item in memberships:
        if item.overlaps_window(start, end):
            by_symbol[item.symbol].append(item)

    rebalance_symbols = _rebalance_encountered_symbols(memberships, start, end)

    rows: list[PitCoverageRow] = []
    for symbol in sorted(by_symbol):
        rows.append(
            _row_for_symbol(
                symbol,
                by_symbol[symbol],
                price_windows,
                master,
                start=start,
                end=end,
                rebalance_encountered=symbol in rebalance_symbols,
                extreme_first_close=extreme_first_close,
            )
        )

    valid_data = 0
    missing = 0
    partial = 0
    unusable = 0
    unresolved = 0
    for row in rows:
        if row.identity_status == RESOLUTION_UNRESOLVED:
            unresolved += 1
        if row.quality_status == QUALITY_UNUSABLE:
            unusable += 1
        if row.coverage_ratio <= 0:
            missing += 1
        elif row.coverage_ratio < 1:
            partial += 1
            if row.quality_status != QUALITY_UNUSABLE:
                valid_data += 1
        elif row.quality_status != QUALITY_UNUSABLE:
            valid_data += 1

    missing_listing = [row for row in rows if not row.local_listing_csv]
    rebalance_missing = [
        row for row in missing_listing if row.rebalance_encountered
    ]
    return PitCoverageReport(
        start=start,
        end=end,
        universe_source=universe_source,
        pit_securities=len(rows),
        rebalance_encountered=len(rebalance_symbols & set(by_symbol)),
        valid_data=valid_data,
        missing=missing,
        partial=partial,
        unusable=unusable,
        unresolved_identity=unresolved,
        rebalance_missing=len(rebalance_missing),
        window_missing_listing_csv=len(missing_listing),
        rows=tuple(rows),
    )


def write_coverage_artifacts(report: PitCoverageReport, output_dir: Path) -> None:
    """Write coverage.csv, coverage.json, and missing.csv. Does not download."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "coverage.csv", report.rows)
    _write_csv(output_dir / "missing.csv", report.missing_rows())
    payload = {
        "window_start": report.start.isoformat(),
        "window_end": report.end.isoformat(),
        "universe_source": report.universe_source,
        "summary": {
            "pit_securities": report.pit_securities,
            "rebalance_encountered": report.rebalance_encountered,
            "valid_data": report.valid_data,
            "missing": report.missing,
            "partial": report.partial,
            "unusable": report.unusable,
            "unresolved_identity": report.unresolved_identity,
            "window_missing_listing_csv": report.window_missing_listing_csv,
            "rebalance_missing_listing_csv": report.rebalance_missing,
        },
        "rows": [row.as_csv_dict() for row in report.rows],
    }
    (output_dir / "coverage.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _row_for_symbol(
    symbol: str,
    intervals: Sequence[ConstituentMembership],
    price_windows: Mapping[str, PriceWindow],
    master: SecurityMaster | None,
    *,
    start: date,
    end: date,
    rebalance_encountered: bool,
    extreme_first_close: Decimal,
) -> PitCoverageRow:
    ordered = tuple(sorted(intervals, key=lambda item: item.start_date))
    pit_start = min(item.start_date for item in ordered)
    pit_end = _latest_end(ordered)
    pit_intervals = "; ".join(_format_interval(item.start_date, item.end_date) for item in ordered)
    expected_start, expected_end = _expected_half_open(ordered, start, end)
    expected_days = max((expected_end - expected_start).days, 0)

    listing_window = price_windows.get(symbol)
    local_listing_csv = listing_window is not None
    vendor_symbol = preferred_vendor_symbol(master, symbol, expected_start, end)
    fetch_names = vendor_fetch_symbols(master, symbol, expected_start, end)
    vendor_window = _first_window(price_windows, fetch_names[1:] if len(fetch_names) > 1 else fetch_names)
    if vendor_window is None:
        vendor_window = listing_window

    identity_status, seed_key, security_id, listing_status = _identity_at(
        master, symbol, expected_start
    )
    recycled = _is_recycled(master, symbol, start, end)
    ticker_change = _is_ticker_change(master, seed_key)

    price_usable = True
    quality_reason = ""
    if vendor_window is not None and vendor_window.first_close is not None:
        if vendor_window.first_close >= extreme_first_close:
            price_usable = False
            quality_reason = "extreme_first_close"

    identity_failed = False
    if identity_status == RESOLUTION_RESOLVED and master is not None:
        vendor_resolution = master.resolve_market_data_symbol(vendor_symbol, expected_start)
        listing_has_vendor = master.has_vendor_mapping(vendor_symbol)
        if not vendor_resolution.is_resolved:
            if local_listing_csv and _windows_overlap_expected(
                listing_window, expected_start, expected_end
            ):
                identity_failed = True
            if listing_window is not None and listing_has_vendor is False:
                if _windows_overlap_expected(listing_window, expected_start, expected_end):
                    identity_failed = True

    valid_overlap = _price_overlap_days(
        vendor_window if price_usable and not identity_failed else None,
        expected_start,
        expected_end,
        master=master,
        vendor_symbol=vendor_symbol,
        listing_ticker=symbol,
    )
    if identity_failed or not price_usable:
        valid_overlap = 0

    ratio = (valid_overlap / expected_days) if expected_days else 0.0
    quality_status, market_status, reason, confidence, notes = _classify(
        symbol=symbol,
        identity_status=identity_status,
        seed_key=seed_key,
        listing_status=listing_status,
        vendor_symbol=vendor_symbol,
        local_listing_csv=local_listing_csv,
        vendor_window=vendor_window,
        listing_window=listing_window,
        expected_start=expected_start,
        expected_end=expected_end,
        coverage_days=valid_overlap,
        coverage_ratio=ratio,
        identity_failed=identity_failed,
        price_usable=price_usable,
        quality_reason=quality_reason,
        recycled=recycled,
        ticker_change=ticker_change,
    )
    return PitCoverageRow(
        security_id=security_id,
        seed_key=seed_key,
        historical_ticker=symbol,
        pit_start=pit_start,
        pit_end=pit_end,
        pit_intervals=pit_intervals,
        identity_status=identity_status,
        market_data_status=market_status,
        vendor_symbol=vendor_symbol,
        price_start=vendor_window.first_date if vendor_window is not None else None,
        price_end=vendor_window.last_date if vendor_window is not None else None,
        coverage_days=valid_overlap,
        expected_days=expected_days,
        coverage_ratio=ratio,
        quality_status=quality_status,
        reason=reason,
        confidence=confidence,
        rebalance_encountered=rebalance_encountered,
        local_listing_csv=local_listing_csv,
        notes=notes,
    )


def _classify(
    *,
    symbol: str,
    identity_status: str,
    seed_key: str | None,
    listing_status: str | None,
    vendor_symbol: str,
    local_listing_csv: bool,
    vendor_window: PriceWindow | None,
    listing_window: PriceWindow | None,
    expected_start: date,
    expected_end: date,
    coverage_days: int,
    coverage_ratio: float,
    identity_failed: bool,
    price_usable: bool,
    quality_reason: str,
    recycled: bool,
    ticker_change: bool,
) -> tuple[str, str, str, str, str]:
    notes: list[str] = []
    other_ticker = vendor_symbol != symbol
    vendor_has_file = vendor_window is not None
    overlap_listing = _windows_overlap_expected(listing_window, expected_start, expected_end)
    overlap_vendor = _windows_overlap_expected(vendor_window, expected_start, expected_end)

    if identity_failed or (not price_usable and overlap_vendor):
        notes.append("identity_mismatch" if identity_failed else quality_reason)
        return (
            QUALITY_UNUSABLE,
            MARKET_UNUSABLE,
            REASON_H_IDENTITY_VALIDATION_FAILED,
            CONFIDENCE_HIGH if identity_status == RESOLUTION_RESOLVED else CONFIDENCE_MEDIUM,
            " ".join(notes) or "Local series fails identity or price-quality validation.",
        )

    if recycled and coverage_days <= 0:
        notes.append("Same listing ticker maps to more than one security.")
        return (
            QUALITY_NA if not overlap_listing else QUALITY_UNUSABLE,
            MARKET_MISSING,
            REASON_C_TICKER_RECYCLED,
            CONFIDENCE_HIGH,
            " ".join(notes),
        )

    if other_ticker and vendor_has_file and coverage_days > 0:
        notes.append(f"Vendor series stored as {vendor_symbol}.")
        quality = QUALITY_VALID if coverage_ratio >= 1 else QUALITY_PARTIAL
        market = MARKET_AVAILABLE_OTHER if coverage_ratio >= 1 else MARKET_PARTIAL
        return (
            quality,
            market,
            REASON_G_DATA_UNDER_OTHER_TICKER,
            CONFIDENCE_HIGH,
            " ".join(notes),
        )

    if other_ticker and not vendor_has_file:
        notes.append(f"Catalog vendor symbol {vendor_symbol} has no local CSV.")
        reason = (
            REASON_E_VENDOR_SYMBOL_DIFFERS
            if "." in symbol
            else REASON_B_TICKER_CHANGE
        )
        return (
            QUALITY_NA,
            MARKET_MISSING,
            reason,
            CONFIDENCE_HIGH if identity_status == RESOLUTION_RESOLVED else CONFIDENCE_MEDIUM,
            " ".join(notes),
        )

    if ticker_change and coverage_days <= 0:
        notes.append("Listing ticker changed; successor vendor series not present locally.")
        return (
            QUALITY_NA,
            MARKET_MISSING,
            REASON_B_TICKER_CHANGE,
            CONFIDENCE_HIGH if identity_status == RESOLUTION_RESOLVED else CONFIDENCE_LOW,
            " ".join(notes),
        )

    if listing_status == STATUS_DELISTED and coverage_days > 0:
        notes.append("Security listing ended; local series covers the PIT interval.")
        quality = QUALITY_VALID if coverage_ratio >= 1 else QUALITY_PARTIAL
        market = MARKET_AVAILABLE if coverage_ratio >= 1 else MARKET_PARTIAL
        return (
            quality,
            market,
            REASON_F_DELISTED,
            CONFIDENCE_HIGH,
            " ".join(notes),
        )

    if listing_status == STATUS_DELISTED and coverage_days <= 0:
        if (
            listing_window is not None
            and listing_window.first_date >= expected_end
        ):
            notes.append(
                "Local series starts after the listing ended; possible ticker recycling."
            )
            return (
                QUALITY_NA,
                MARKET_MISSING,
                REASON_C_TICKER_RECYCLED,
                CONFIDENCE_HIGH,
                " ".join(notes),
            )
        notes.append("Security listing ended; no local vendor series for the PIT interval.")
        return (
            QUALITY_NA,
            MARKET_MISSING,
            REASON_A_UNAVAILABLE if identity_status == RESOLUTION_RESOLVED else REASON_D_UNRESOLVED_IDENTITY,
            CONFIDENCE_HIGH if identity_status == RESOLUTION_RESOLVED else CONFIDENCE_LOW,
            " ".join(notes),
        )

    if coverage_days <= 0 and not local_listing_csv and identity_status == RESOLUTION_UNRESOLVED:
        if "." in symbol:
            notes.append("Share-class punctuation; Yahoo typically uses hyphen form.")
            return (
                QUALITY_NA,
                MARKET_MISSING,
                REASON_E_VENDOR_SYMBOL_DIFFERS,
                CONFIDENCE_MEDIUM,
                " ".join(notes),
            )
        notes.append("No Security Master row and no local CSV under the PIT ticker.")
        return (
            QUALITY_NA,
            MARKET_MISSING,
            REASON_D_UNRESOLVED_IDENTITY,
            CONFIDENCE_LOW,
            " ".join(notes),
        )

    if coverage_days <= 0:
        notes.append("No valid prices overlapping the PIT membership interval.")
        reason = REASON_I_INSUFFICIENT_EVIDENCE
        if identity_status == RESOLUTION_UNRESOLVED:
            reason = REASON_D_UNRESOLVED_IDENTITY
        return (QUALITY_NA, MARKET_MISSING, reason, CONFIDENCE_LOW, " ".join(notes))

    if coverage_ratio < 1:
        notes.append("Local prices overlap only part of the PIT membership interval.")
        if listing_status == STATUS_DELISTED:
            reason = REASON_F_DELISTED
        elif identity_status == RESOLUTION_UNRESOLVED:
            reason = REASON_D_UNRESOLVED_IDENTITY
        else:
            reason = REASON_I_INSUFFICIENT_EVIDENCE
        return (
            QUALITY_PARTIAL,
            MARKET_PARTIAL,
            reason,
            CONFIDENCE_MEDIUM if identity_status == RESOLUTION_RESOLVED else CONFIDENCE_LOW,
            " ".join(notes),
        )

    notes.append("Local prices cover the PIT membership interval in this window.")
    if identity_status == RESOLUTION_UNRESOLVED:
        return (
            QUALITY_VALID,
            MARKET_AVAILABLE,
            REASON_D_UNRESOLVED_IDENTITY,
            CONFIDENCE_LOW,
            " ".join(notes),
        )
    return (
        QUALITY_VALID,
        MARKET_AVAILABLE,
        "",
        CONFIDENCE_HIGH,
        " ".join(notes),
    )


def _identity_at(
    master: SecurityMaster | None,
    symbol: str,
    as_of: date,
) -> tuple[str, str | None, int | None, str | None]:
    if master is None:
        return RESOLUTION_UNRESOLVED, None, None, None
    listing = master.resolve_security(symbol, as_of)
    if not listing.is_resolved or listing.security is None:
        return RESOLUTION_UNRESOLVED, None, None, None
    security = listing.security
    return RESOLUTION_RESOLVED, security.seed_key, security.security_id, security.status


def _is_recycled(master: SecurityMaster | None, ticker: str, start: date, end: date) -> bool:
    if master is None:
        return False
    keys_fn = getattr(master, "listing_seed_keys", None)
    if callable(keys_fn):
        return len(keys_fn(ticker, start, end)) > 1
    return False


def _is_ticker_change(master: SecurityMaster | None, seed_key: str | None) -> bool:
    if master is None or not seed_key:
        return False
    history = master.get_ticker_history(seed_key)
    listing_tickers = {item.ticker for item in history}
    return len(listing_tickers) > 1


def _expected_half_open(
    intervals: Sequence[ConstituentMembership],
    window_start: date,
    window_end: date,
) -> tuple[date, date]:
    window_end_exclusive = window_end + timedelta(days=1)
    starts: list[date] = []
    ends: list[date] = []
    for item in intervals:
        lo = max(item.start_date, window_start)
        hi = window_end_exclusive if item.end_date is None else min(item.end_date, window_end_exclusive)
        if lo < hi:
            starts.append(lo)
            ends.append(hi)
    if not starts:
        return window_start, window_start
    return min(starts), max(ends)


def _price_overlap_days(
    window: PriceWindow | None,
    expected_start: date,
    expected_end: date,
    *,
    master: SecurityMaster | None,
    vendor_symbol: str,
    listing_ticker: str,
) -> int:
    if window is None:
        return 0
    price_start = window.first_date
    price_end_exclusive = window.last_date + timedelta(days=1)
    if master is not None:
        vendor = master.resolve_market_data_symbol(vendor_symbol, window.first_date)
        listing = master.resolve_security(listing_ticker, expected_start)
        if listing.is_resolved and listing.security is not None:
            yahoo_rows = [
                item
                for item in getattr(master, "tickers", lambda: ())()
                if item.scheme == "yahoo"
                and item.ticker == normalize_symbol(vendor_symbol)
                and item.seed_key == listing.security.seed_key
            ]
            if yahoo_rows:
                row = yahoo_rows[0]
                price_start = max(price_start, row.valid_from)
                if row.valid_to is not None:
                    price_end_exclusive = min(price_end_exclusive, row.valid_to)
            elif not vendor.is_resolved:
                return 0
    lo = max(price_start, expected_start)
    hi = min(price_end_exclusive, expected_end)
    if lo >= hi:
        return 0
    return (hi - lo).days


def _windows_overlap_expected(
    window: PriceWindow | None,
    expected_start: date,
    expected_end: date,
) -> bool:
    if window is None:
        return False
    return window.first_date < expected_end and (window.last_date + timedelta(days=1)) > expected_start


def _first_window(
    windows: Mapping[str, PriceWindow],
    symbols: Sequence[str],
) -> PriceWindow | None:
    for symbol in symbols:
        found = windows.get(symbol)
        if found is not None:
            return found
    return None


def _latest_end(periods: Sequence[ConstituentMembership]) -> date | None:
    if any(item.end_date is None for item in periods):
        return None
    ends = [item.end_date for item in periods if item.end_date is not None]
    return max(ends) if ends else None


def _format_interval(start: date, end: date | None) -> str:
    end_text = "open" if end is None else end.isoformat()
    return f"{start.isoformat()}→{end_text}"


def _rebalance_encountered_symbols(
    memberships: Sequence[ConstituentMembership],
    start: date,
    end: date,
) -> set[str]:
    encounter_start = max(start, REBALANCE_ENCOUNTER_START)
    dates = month_starts(encounter_start, end)
    symbols: set[str] = set()
    for as_of in dates:
        for item in memberships:
            if item.contains(as_of):
                symbols.add(item.symbol)
    return symbols


def _write_csv(path: Path, rows: Sequence[PitCoverageRow]) -> None:
    import csv

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())
