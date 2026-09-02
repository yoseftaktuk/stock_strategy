from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class MarketDataImportStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    FAILED = "FAILED"
    EMPTY = "EMPTY"


class MarketDataImportOrigin(str, Enum):
    DOWNLOADED = "downloaded"
    CACHED = "cached"
    DATABASE = "database"
    EMPTY = "empty"
    FAILED = "failed"


@dataclass(frozen=True)
class MarketDataImportSummary:
    symbol: str
    rows_read: int
    rows_inserted: int
    duplicates: int
    invalid_rows: int
    start: date
    end: date
    status: MarketDataImportStatus
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    bars_in_database: int = 0
    origin: MarketDataImportOrigin = MarketDataImportOrigin.DOWNLOADED

    def __str__(self) -> str:
        first = self.first_timestamp.date().isoformat() if self.first_timestamp else "n/a"
        last = self.last_timestamp.date().isoformat() if self.last_timestamp else "n/a"
        lines = [
            "Historical Data Import",
            f"Symbol: {self.symbol}",
            f"Rows: {self.rows_read}",
            f"Rows inserted: {self.rows_inserted}",
            f"Bars in database: {self.bars_in_database}",
            f"First: {first}",
            f"Last: {last}",
            f"Duplicates: {self.duplicates}",
            f"Missing/Invalid Rows: {self.invalid_rows}",
            f"Origin: {self.origin.value}",
            f"Status: {self.status.value}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {warning}" for warning in self.warnings)
        return "\n".join(lines)
