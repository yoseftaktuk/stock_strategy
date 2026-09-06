"""Identity observation and position-key primitives.

Canonical runtime identity is ``security_id``. Ticker is listing/display only.
UNRESOLVED never carries a guessed security_id.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.exceptions import DomainValidationError
from app.domain.models.listing import Listing, unknown_occupancy_listing_id
from app.domain.models.security import RESOLUTION_RESOLVED, RESOLUTION_UNRESOLVED

POSITION_KEY_SECURITY = "security"
POSITION_KEY_LISTING = "listing"
ALLOWED_POSITION_KEY_KINDS = frozenset({POSITION_KEY_SECURITY, POSITION_KEY_LISTING})


def _normalize_token(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field} must not be empty")
    return normalized


@dataclass(frozen=True)
class PositionKey:
    """Broker/accounting join key. Not a ticker.

    RESOLVED positions key on security_id so ticker changes stay one position.
    UNRESOLVED positions key on listing occupancy so recycled tickers do not merge.
    """

    kind: str
    value: str

    def __post_init__(self) -> None:
        kind = _normalize_token(self.kind, field="kind").lower()
        if kind not in ALLOWED_POSITION_KEY_KINDS:
            raise DomainValidationError(
                f"kind must be one of {sorted(ALLOWED_POSITION_KEY_KINDS)}"
            )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", _normalize_token(self.value, field="value"))

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}"

    @classmethod
    def for_security(cls, security_id: str) -> PositionKey:
        return cls(kind=POSITION_KEY_SECURITY, value=security_id)

    @classmethod
    def for_listing(cls, listing_id: str) -> PositionKey:
        return cls(kind=POSITION_KEY_LISTING, value=listing_id)


@dataclass(frozen=True)
class IdentityRef:
    """Identity of a listing observation at an as-of date.

    RESOLVED: security_id plus listing identity and ticker_as_of.
    UNRESOLVED: listing identity and ticker_as_of; security_id is None.
    """

    status: str
    ticker_as_of: str
    listing: Listing
    security_id: str | None = None

    def __post_init__(self) -> None:
        status = self.status.strip().upper()
        if status not in {RESOLUTION_RESOLVED, RESOLUTION_UNRESOLVED}:
            raise DomainValidationError("status must be RESOLVED or UNRESOLVED")
        ticker_as_of = _normalize_token(self.ticker_as_of, field="ticker_as_of").upper()
        object.__setattr__(self, "ticker_as_of", ticker_as_of)
        object.__setattr__(self, "status", status)
        security_id = self.security_id.strip() if self.security_id is not None else None
        if security_id == "":
            raise DomainValidationError("security_id must not be empty")
        object.__setattr__(self, "security_id", security_id)
        if status == RESOLUTION_RESOLVED:
            if security_id is None:
                raise DomainValidationError("RESOLVED identity requires a security_id")
            if self.listing.security_id is None:
                raise DomainValidationError("RESOLVED identity requires a listing security_id")
            if self.listing.security_id != security_id:
                raise DomainValidationError("listing.security_id must match identity security_id")
        else:
            if security_id is not None:
                raise DomainValidationError("UNRESOLVED identity must not carry a security_id")
            if self.listing.security_id is not None:
                raise DomainValidationError("UNRESOLVED identity must not carry a listing security_id")
        if ticker_as_of != self.listing.ticker:
            raise DomainValidationError("ticker_as_of must match the listing ticker")

    @property
    def is_resolved(self) -> bool:
        return self.status == RESOLUTION_RESOLVED and self.security_id is not None

    def position_key(self) -> PositionKey:
        if self.is_resolved:
            if self.security_id is None:
                raise DomainValidationError("RESOLVED identity requires a security_id")
            return PositionKey.for_security(self.security_id)
        return PositionKey.for_listing(self.listing.listing_id)

    @classmethod
    def resolved(cls, *, security_id: str, listing: Listing, ticker_as_of: str) -> IdentityRef:
        return cls(
            status=RESOLUTION_RESOLVED,
            ticker_as_of=ticker_as_of,
            listing=listing,
            security_id=security_id,
        )

    @classmethod
    def unresolved(cls, *, listing: Listing, ticker_as_of: str) -> IdentityRef:
        return cls(
            status=RESOLUTION_UNRESOLVED,
            ticker_as_of=ticker_as_of,
            listing=listing,
            security_id=None,
        )

    @property
    def listing_id(self) -> str:
        return self.listing.listing_id

    @property
    def position_key_value(self) -> str:
        return str(self.position_key())


def require_matching_ticker(symbol: str, identity: IdentityRef | None) -> None:
    """Reject an identity attached to a different execution ticker."""
    if identity is None:
        return
    if identity.ticker_as_of != symbol.strip().upper():
        raise DomainValidationError("identity ticker_as_of must match symbol")


class IdentityCarrier:
    """Expose a stored IdentityRef as additive identity fields.

    Subclasses define ``identity: IdentityRef | None = None``. Identity is
    resolved once and copied; these properties never re-resolve.
    """

    identity: IdentityRef | None

    @property
    def security_id(self) -> str | None:
        identity = self.identity
        return None if identity is None else identity.security_id

    @property
    def listing_id(self) -> str | None:
        identity = self.identity
        if identity is None:
            return None
        return identity.listing_id

    @property
    def position_key(self) -> str | None:
        identity = self.identity
        if identity is None:
            return None
        return identity.position_key_value


def position_key_for(carrier: IdentityCarrier) -> str:
    """Canonical broker booking key. Never a raw ticker.

    Uses identity already attached to ``carrier``. Does not resolve.
    When identity is missing, books on the occupancy-unknown listing key for
    the execution ticker so unidentified orders still do not use ticker as
    the dict key.
    """
    key = carrier.position_key
    if key is not None:
        return key
    symbol = getattr(carrier, "symbol", None)
    if not isinstance(symbol, str) or not symbol.strip():
        raise DomainValidationError("booking key requires an attached identity or symbol")
    return str(
        PositionKey.for_listing(unknown_occupancy_listing_id(ticker=symbol, exchange=None))
    )
