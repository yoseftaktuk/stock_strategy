from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.models.market_bar import MarketBar


@dataclass(frozen=True)
class MarketDataFetchResult:
    bars: tuple[MarketBar, ...]
    rows_read: int
    invalid_rows: tuple[str, ...]
    duplicate_timestamps: int
    from_cache: bool = False


class MarketDataProvider(Protocol):
    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[MarketBar]:
        """Return historical market bars for a symbol."""

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> MarketDataFetchResult:
        """Return bars plus row-level import diagnostics for a symbol."""
