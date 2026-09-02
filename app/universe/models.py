"""Canonical constituent membership intervals.

Intervals are half-open: ``start_date <= as_of < end_date``. A ``None`` end date
means the membership is still active. Separate source periods for the same
symbol must not be merged.
"""

from dataclasses import dataclass
from datetime import date, datetime

from app.data.validation import normalize_symbol
from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class ConstituentMembership:
    """A period during which ``symbol`` was a constituent of an index."""

    symbol: str
    start_date: date
    end_date: date | None = None
    company_name: str | None = None
    source: str | None = None
    source_version: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized = normalize_symbol(self.symbol)
        if not normalized:
            raise DomainValidationError("symbol must not be empty")
        object.__setattr__(self, "symbol", normalized)
        if self.end_date is not None and self.start_date >= self.end_date:
            raise DomainValidationError("start_date must be earlier than end_date")
        if self.company_name is not None:
            object.__setattr__(self, "company_name", self.company_name.strip() or None)
        if self.source is not None:
            object.__setattr__(self, "source", self.source.strip() or None)
        if self.source_version is not None:
            object.__setattr__(self, "source_version", self.source_version.strip() or None)

    def contains(self, as_of: date) -> bool:
        """Return True if ``as_of`` falls in ``[start_date, end_date)``."""
        if self.start_date > as_of:
            return False
        if self.end_date is None:
            return True
        return as_of < self.end_date

    def overlaps_window(self, start: date, end: date) -> bool:
        """Return True if this interval overlaps the inclusive ``[start, end]`` window."""
        if self.start_date > end:
            return False
        if self.end_date is None:
            return True
        return start < self.end_date
