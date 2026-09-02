"""Application-facing universe orchestration.

The service does not parse source files. Source adapters produce normalized
intervals; the repository persists them; query providers answer point-in-time
membership without using market data.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.database.repositories.interfaces import SP500ConstituentRepository
from app.universe.exceptions import UniverseValidationError
from app.universe.interface import UniverseProvider
from app.universe.memory import InMemoryUniverseProvider
from app.universe.models import ConstituentMembership
from app.universe.providers.query import HistoricalSP500UniverseProvider
from app.universe.validation import validate_memberships


@dataclass(frozen=True)
class UniverseImportSummary:
    source: str
    source_version: str
    raw_records: int
    normalized_intervals: int
    duplicate_intervals: int
    invalid_intervals: int
    overlapping_intervals: int
    inserted: int
    existing: int
    invalid_details: tuple[str, ...] = field(default_factory=tuple)
    overlapping_details: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.invalid_intervals == 0 and self.overlapping_intervals == 0

    def format(self) -> str:
        lines = [
            "Historical S&P 500 Universe Import",
            f"Source: {self.source}",
            f"Source version: {self.source_version}",
            f"Raw records: {self.raw_records}",
            f"Normalized intervals: {self.normalized_intervals}",
            f"Duplicate intervals: {self.duplicate_intervals}",
            f"Invalid intervals: {self.invalid_intervals}",
            f"Overlapping intervals: {self.overlapping_intervals}",
            f"Inserted: {self.inserted}",
            f"Existing: {self.existing}",
        ]
        if self.invalid_details:
            lines.append("Invalid:")
            lines.extend(f"  - {item}" for item in self.invalid_details)
        if self.overlapping_details:
            lines.append("Overlapping:")
            lines.extend(f"  - {item}" for item in self.overlapping_details)
        return "\n".join(lines)


class UniverseService:
    def __init__(
        self,
        repository: SP500ConstituentRepository,
        provider: UniverseProvider | None = None,
    ) -> None:
        self._repository = repository
        self._provider = provider or HistoricalSP500UniverseProvider(repository)

    def get_symbols(self, as_of: date) -> list[str]:
        return self._provider.get_symbols(as_of)

    def symbols_overlapping_window(self, start: date, end: date) -> list[str]:
        selected = [
            item.symbol
            for item in self._repository.get_all_memberships()
            if item.overlaps_window(start, end)
        ]
        return sorted(set(selected))

    def snapshot_provider(self, *, current_only: bool = False) -> InMemoryUniverseProvider:
        """Copy memberships into memory so backtests do not query the database."""
        return InMemoryUniverseProvider(
            self._repository.get_all_memberships(),
            current_only=current_only,
        )

    def persist_memberships(
        self,
        memberships: Sequence[ConstituentMembership],
        *,
        source: str,
        source_version: str,
        raw_records: int,
    ) -> UniverseImportSummary:
        report = validate_memberships(memberships)
        invalid_details = tuple(issue.format() for issue in report.invalid)
        overlapping_details = tuple(issue.format() for issue in report.overlapping)
        if report.has_blocking_errors:
            summary = UniverseImportSummary(
                source=source,
                source_version=source_version,
                raw_records=raw_records,
                normalized_intervals=len(memberships),
                duplicate_intervals=len(report.duplicates),
                invalid_intervals=len(report.invalid),
                overlapping_intervals=len(report.overlapping),
                inserted=0,
                existing=0,
                invalid_details=invalid_details,
                overlapping_details=overlapping_details,
            )
            raise UniverseValidationError(
                summary.format(),
                issues=invalid_details + overlapping_details,
            )

        inserted, existing = self._repository.upsert_memberships(report.valid)
        return UniverseImportSummary(
            source=source,
            source_version=source_version,
            raw_records=raw_records,
            normalized_intervals=len(report.valid),
            duplicate_intervals=len(report.duplicates),
            invalid_intervals=0,
            overlapping_intervals=0,
            inserted=inserted,
            existing=existing,
        )
