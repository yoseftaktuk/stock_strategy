"""Configurable per-rebalance universe audit CSV builders.

Detail dumps are opt-in so a long S&P 500 run does not write ~60k rows by default.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.universe.audit import UniverseAuditReport, memberships_as_of
from app.universe.models import ConstituentMembership

SUMMARY_FIELDS = (
    "rebalance_date",
    "universe_size",
    "new_constituents",
    "removed_constituents",
    "invalid_constituents",
    "suspicious_constituents",
)
DETAIL_FIELDS = (
    "rebalance_date",
    "symbol",
    "eligible",
    "membership_start",
    "membership_end",
    "eligibility_reason",
)


@dataclass(frozen=True)
class UniverseSummaryRow:
    rebalance_date: date
    universe_size: int
    new_constituents: int
    removed_constituents: int
    invalid_constituents: int
    suspicious_constituents: int


@dataclass(frozen=True)
class UniverseDetailRow:
    rebalance_date: date
    symbol: str
    eligible: bool
    membership_start: date | None
    membership_end: date | None
    eligibility_reason: str


def summary_rows(report: UniverseAuditReport) -> list[UniverseSummaryRow]:
    rows: list[UniverseSummaryRow] = []
    previous: set[str] = set()
    for rebalance in report.rebalances:
        current = set(rebalance.symbols)
        rows.append(
            UniverseSummaryRow(
                rebalance_date=rebalance.as_of,
                universe_size=len(rebalance.symbols),
                new_constituents=len(current - previous),
                removed_constituents=len(previous - current) if previous else 0,
                invalid_constituents=len(rebalance.invalid),
                suspicious_constituents=len(rebalance.suspicious),
            )
        )
        previous = current
    return rows


def detail_rows(
    report: UniverseAuditReport,
    *,
    changes_only: bool = False,
) -> list[UniverseDetailRow]:
    rows: list[UniverseDetailRow] = []
    previous: set[str] = set()
    by_symbol: dict[str, list[ConstituentMembership]] = {}
    for item in report.memberships:
        by_symbol.setdefault(item.symbol, []).append(item)

    for rebalance in report.rebalances:
        current = set(rebalance.symbols)
        if changes_only:
            symbols = sorted((current - previous) | (previous - current))
        else:
            symbols = list(rebalance.symbols)
        invalid = set(rebalance.invalid)
        suspicious = set(rebalance.suspicious)
        for symbol in symbols:
            eligible = symbol in current
            active = _active_membership(by_symbol.get(symbol, ()), rebalance.as_of)
            reason = _eligibility_reason(
                eligible=eligible,
                in_previous=symbol in previous,
                invalid=symbol in invalid,
                suspicious=symbol in suspicious,
                membership=active,
                as_of=rebalance.as_of,
            )
            rows.append(
                UniverseDetailRow(
                    rebalance_date=rebalance.as_of,
                    symbol=symbol,
                    eligible=eligible,
                    membership_start=active.start_date if active is not None else None,
                    membership_end=active.end_date if active is not None else None,
                    eligibility_reason=reason,
                )
            )
        previous = current
    return rows


def write_summary_csv(path: Path, report: UniverseAuditReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in summary_rows(report):
            writer.writerow(
                {
                    "rebalance_date": row.rebalance_date.isoformat(),
                    "universe_size": row.universe_size,
                    "new_constituents": row.new_constituents,
                    "removed_constituents": row.removed_constituents,
                    "invalid_constituents": row.invalid_constituents,
                    "suspicious_constituents": row.suspicious_constituents,
                }
            )


def write_detail_csv(
    path: Path,
    report: UniverseAuditReport,
    *,
    changes_only: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        for row in detail_rows(report, changes_only=changes_only):
            writer.writerow(
                {
                    "rebalance_date": row.rebalance_date.isoformat(),
                    "symbol": row.symbol,
                    "eligible": str(row.eligible).lower(),
                    "membership_start": row.membership_start.isoformat() if row.membership_start else "",
                    "membership_end": row.membership_end.isoformat() if row.membership_end else "",
                    "eligibility_reason": row.eligibility_reason,
                }
            )


def _active_membership(
    periods: Sequence[ConstituentMembership],
    as_of: date,
) -> ConstituentMembership | None:
    matches = memberships_as_of(periods, as_of)
    return matches[0] if matches else None


def _eligibility_reason(
    *,
    eligible: bool,
    in_previous: bool,
    invalid: bool,
    suspicious: bool,
    membership: ConstituentMembership | None,
    as_of: date,
) -> str:
    if invalid:
        return "invalid_interval"
    if not eligible:
        if membership is None:
            return "left_index" if in_previous else "not_a_member"
        if membership.start_date > as_of:
            return "before_membership_start"
        if membership.end_date is not None and as_of >= membership.end_date:
            return "after_membership_end"
        return "not_eligible"
    if not in_previous:
        prefix = "joined"
    else:
        prefix = "member"
    if suspicious:
        return f"{prefix};suspicious"
    return prefix
