"""Corporate-action event types. Semantics only — not a data provider.

Events must come from an explicit source. They are never inferred from
``adjusted_close`` or from Close/Adj Close ratios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityRef


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    CASH_DIVIDEND = "CASH_DIVIDEND"
    CASH_ACQUISITION = "CASH_ACQUISITION"
    SHARE_CONVERSION = "SHARE_CONVERSION"
    DELISTING = "DELISTING"
    RENAME = "RENAME"
    NO_ACTION = "NO_ACTION"


class FractionalSharePolicy(str, Enum):
    """How leftover shares after a split/reverse split are handled."""

    KEEP_FRACTION = "KEEP_FRACTION"
    CASH_IN_LIEU = "CASH_IN_LIEU"


class ActionApplication(str, Enum):
    APPLIED = "APPLIED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class CorporateAction:
    """One dated corporate-action event for a known instrument or listing.

    ``security_id`` / ``listing_id`` are identity keys when known. ``ticker``
    is display/execution only and must not be used to alias securities.
    ``factor`` is the share multiple for splits (2 for 2-for-1, 0.5 for 1-for-2).
    ``amount`` is cash per share for dividends or cash acquisitions.
    """

    action_type: CorporateActionType
    effective_date: date
    security_id: str | None = None
    listing_id: str | None = None
    ticker: str | None = None
    factor: Decimal | None = None
    amount: Decimal | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.ticker is not None:
            object.__setattr__(self, "ticker", self.ticker.strip().upper() or None)
        if self.security_id is not None:
            token = self.security_id.strip()
            if not token:
                raise DomainValidationError("security_id must not be empty")
            object.__setattr__(self, "security_id", token)
        if self.listing_id is not None:
            token = self.listing_id.strip()
            if not token:
                raise DomainValidationError("listing_id must not be empty")
            object.__setattr__(self, "listing_id", token)
        if self.factor is not None and self.factor <= 0:
            raise DomainValidationError("factor must be > 0")
        if self.amount is not None and self.amount < 0:
            raise DomainValidationError("amount must be >= 0")
        if not self.source.strip():
            object.__setattr__(self, "source", "")
        else:
            object.__setattr__(self, "source", self.source.strip())


@dataclass(frozen=True)
class AccountingSnapshot:
    """Position plus cash for corporate-action math. Not a broker state object."""

    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    cash: Decimal
    symbol: str
    identity: IdentityRef | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.quantity < 0:
            raise DomainValidationError("quantity must be non-negative")
        if self.average_price < 0:
            raise DomainValidationError("average_price must be non-negative")
        if self.market_price < 0:
            raise DomainValidationError("market_price must be non-negative")

    @property
    def market_value(self) -> Decimal:
        return self.quantity * self.market_price

    @property
    def economic_value(self) -> Decimal:
        return self.cash + self.market_value

    def position_key(self) -> str | None:
        if self.identity is None:
            return None
        return str(self.identity.position_key())
