"""Tradable listing interval. Distinct from Security (economic instrument).

A listing is one occupancy of a ticker on an exchange. Recycled tickers are
separate listings. Half-open validity: ``valid_from <= as_of < valid_to``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.exceptions import DomainValidationError

UNKNOWN_EXCHANGE = "_"
UNKNOWN_OCCUPANCY_TOKEN = "occupancy-unknown"


def _normalize_token(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field} must not be empty")
    return normalized


def _exchange_token(exchange: str | None) -> str:
    if exchange is None:
        return UNKNOWN_EXCHANGE
    normalized = exchange.strip().upper()
    return normalized if normalized else UNKNOWN_EXCHANGE


def occupancy_listing_id(*, ticker: str, exchange: str | None, valid_from: date) -> str:
    """Stable listing identity for a known occupancy. Ticker alone is not enough."""
    return f"{_exchange_token(exchange)}:{ticker}:{valid_from.isoformat()}"


def unknown_occupancy_listing_id(*, ticker: str, exchange: str | None) -> str:
    """Fallback when occupancy bounds are unknown. Unsafe for ticker recycle."""
    return f"{_exchange_token(exchange)}:{ticker}:{UNKNOWN_OCCUPANCY_TOKEN}"


@dataclass(frozen=True)
class Listing:
    """One tradable name of a security (or an unresolved occupancy) over an interval."""

    ticker: str
    valid_from: date
    valid_to: date | None = None
    listing_id: str = ""
    security_id: str | None = None
    exchange: str | None = None

    def __post_init__(self) -> None:
        ticker = _normalize_token(self.ticker, field="ticker").upper()
        object.__setattr__(self, "ticker", ticker)
        exchange = self.exchange.strip().upper() if self.exchange is not None else None
        object.__setattr__(self, "exchange", exchange or None)
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            raise DomainValidationError("valid_from must be earlier than valid_to")
        security_id = self.security_id.strip() if self.security_id is not None else None
        if security_id == "":
            raise DomainValidationError("security_id must not be empty")
        object.__setattr__(self, "security_id", security_id)
        listing_id = self.listing_id.strip()
        if not listing_id:
            listing_id = occupancy_listing_id(
                ticker=ticker,
                exchange=self.exchange,
                valid_from=self.valid_from,
            )
        object.__setattr__(self, "listing_id", listing_id)

    def contains(self, as_of: date) -> bool:
        """Return True if ``as_of`` falls in ``[valid_from, valid_to)``."""
        if self.valid_from > as_of:
            return False
        if self.valid_to is None:
            return True
        return as_of < self.valid_to

    @classmethod
    def unknown_occupancy(
        cls,
        ticker: str,
        as_of: date,
        *,
        exchange: str | None = None,
    ) -> Listing:
        """UNRESOLVED observation with no occupancy evidence.

        ``valid_from`` records the observation date, not a listing start.
        ``listing_id`` is occupancy-unknown so recycle cannot be distinguished
        until a real occupancy is supplied.
        """
        normalized = _normalize_token(ticker, field="ticker").upper()
        return cls(
            ticker=normalized,
            valid_from=as_of,
            valid_to=None,
            listing_id=unknown_occupancy_listing_id(ticker=normalized, exchange=exchange),
            security_id=None,
            exchange=exchange,
        )

    @property
    def occupancy_known(self) -> bool:
        return not self.listing_id.endswith(f":{UNKNOWN_OCCUPANCY_TOKEN}")
