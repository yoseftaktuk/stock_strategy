"""Membership interval validation.

Invalid and overlapping intervals are reported and must not be persisted.
Adjacent half-open intervals are allowed. Distinct source periods are never merged.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.universe.models import ConstituentMembership


@dataclass(frozen=True)
class MembershipIssue:
    message: str
    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def format(self) -> str:
        parts = [self.message]
        if self.symbol:
            parts.append(f"symbol={self.symbol}")
        if self.start_date is not None:
            parts.append(f"start={self.start_date.isoformat()}")
        if self.end_date is not None:
            parts.append(f"end={self.end_date.isoformat()}")
        return " ".join(parts)


@dataclass(frozen=True)
class MembershipValidationReport:
    valid: tuple[ConstituentMembership, ...]
    duplicates: tuple[ConstituentMembership, ...]
    invalid: tuple[MembershipIssue, ...] = field(default_factory=tuple)
    overlapping: tuple[MembershipIssue, ...] = field(default_factory=tuple)

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.invalid or self.overlapping)


def _interval_key(membership: ConstituentMembership) -> tuple[str, date, date | None]:
    return (membership.symbol, membership.start_date, membership.end_date)


def _effective_end(membership: ConstituentMembership) -> date:
    return membership.end_date if membership.end_date is not None else date.max


def intervals_overlap(left: ConstituentMembership, right: ConstituentMembership) -> bool:
    """Half-open overlap: adjacent intervals that share a boundary do not overlap."""
    if left.symbol != right.symbol:
        return False
    return left.start_date < _effective_end(right) and right.start_date < _effective_end(left)


def validate_memberships(memberships: Sequence[ConstituentMembership]) -> MembershipValidationReport:
    """Detect exact duplicates and per-symbol overlapping intervals."""
    duplicates: list[ConstituentMembership] = []
    unique: list[ConstituentMembership] = []
    seen: set[tuple[str, date, date | None]] = set()
    for membership in memberships:
        key = _interval_key(membership)
        if key in seen:
            duplicates.append(membership)
            continue
        seen.add(key)
        unique.append(membership)

    overlapping: list[MembershipIssue] = []
    by_symbol: dict[str, list[ConstituentMembership]] = defaultdict(list)
    for membership in unique:
        by_symbol[membership.symbol].append(membership)

    for symbol, periods in by_symbol.items():
        ordered = sorted(periods, key=lambda item: (item.start_date, _effective_end(item)))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if intervals_overlap(current, other):
                    overlapping.append(
                        MembershipIssue(
                            "overlapping membership intervals",
                            symbol=symbol,
                            start_date=current.start_date,
                            end_date=current.end_date,
                        )
                    )
                    overlapping.append(
                        MembershipIssue(
                            "overlapping membership intervals",
                            symbol=symbol,
                            start_date=other.start_date,
                            end_date=other.end_date,
                        )
                    )

    return MembershipValidationReport(
        valid=tuple(unique),
        duplicates=tuple(duplicates),
        overlapping=tuple(overlapping),
    )
