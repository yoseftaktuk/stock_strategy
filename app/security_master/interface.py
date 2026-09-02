"""Security Master query protocol.

PIT membership and market-data storage remain separate. This protocol answers
identity questions only.
"""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domain.models.security import SCHEME_YAHOO, Resolution, Security, SecurityTicker


class SecurityMaster(Protocol):
    def resolve_security(self, ticker: str, as_of: date) -> Resolution:
        """Which listing security did ``ticker`` represent on ``as_of``?"""

    def resolve_market_data_symbol(
        self,
        symbol: str,
        as_of: date,
        source: str = SCHEME_YAHOO,
    ) -> Resolution:
        """Which security does a vendor market-data symbol represent on ``as_of``?"""

    def get_ticker_history(self, seed_key: str) -> Sequence[SecurityTicker]:
        """Listing ticker intervals for a security, oldest first."""

    def get_security(self, seed_key: str) -> Security | None:
        """Return the catalog security for ``seed_key``, if present."""

    def has_vendor_mapping(self, symbol: str, source: str = SCHEME_YAHOO) -> bool:
        """Return True if the catalog has any vendor interval for ``symbol``."""

    def tickers(self) -> Sequence[SecurityTicker]:
        """All catalog ticker intervals (listing and vendor schemes)."""
