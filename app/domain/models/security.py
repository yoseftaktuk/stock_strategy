"""Canonical security identity types.

A ticker is time-varying. A security is the economic/instrument identity.
Ticker validity uses half-open intervals: ``valid_from <= as_of < valid_to``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.exceptions import DomainValidationError

SCHEME_LISTING = "listing"
SCHEME_YAHOO = "yahoo"
ALLOWED_SCHEMES = frozenset({SCHEME_LISTING, SCHEME_YAHOO})

STATUS_ACTIVE = "ACTIVE"
STATUS_DELISTED = "DELISTED"
ALLOWED_STATUSES = frozenset({STATUS_ACTIVE, STATUS_DELISTED})

SECURITY_TYPE_COMMON_STOCK = "COMMON_STOCK"

RESOLUTION_RESOLVED = "RESOLVED"
RESOLUTION_UNRESOLVED = "UNRESOLVED"


def _normalize_token(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field} must not be empty")
    return normalized


@dataclass(frozen=True)
class Security:
    """Canonical security identity. ``seed_key`` is stable; ``security_id`` is the DB key."""

    seed_key: str
    display_name: str
    security_type: str = SECURITY_TYPE_COMMON_STOCK
    currency: str = "USD"
    status: str = STATUS_ACTIVE
    notes: str | None = None
    security_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_key", _normalize_token(self.seed_key, field="seed_key"))
        object.__setattr__(
            self, "display_name", _normalize_token(self.display_name, field="display_name")
        )
        object.__setattr__(
            self,
            "security_type",
            _normalize_token(self.security_type, field="security_type").upper(),
        )
        object.__setattr__(self, "currency", _normalize_token(self.currency, field="currency").upper())
        status = _normalize_token(self.status, field="status").upper()
        if status not in ALLOWED_STATUSES:
            raise DomainValidationError(f"status must be one of {sorted(ALLOWED_STATUSES)}")
        object.__setattr__(self, "status", status)
        if self.notes is not None:
            object.__setattr__(self, "notes", self.notes.strip() or None)


@dataclass(frozen=True)
class SecurityTicker:
    """Time-bounded ticker assignment for a security.

    ``scheme`` distinguishes listing tickers from vendor (Yahoo) symbols.
    ``continuity`` records that the vendor remaps predecessor history of the
    *same* security onto this ticker. It does not invent identity.
    """

    seed_key: str
    scheme: str
    ticker: str
    valid_from: date
    valid_to: date | None = None
    continuity: bool = False
    source: str | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_key", _normalize_token(self.seed_key, field="seed_key"))
        scheme = _normalize_token(self.scheme, field="scheme").lower()
        if scheme not in ALLOWED_SCHEMES:
            raise DomainValidationError(f"scheme must be one of {sorted(ALLOWED_SCHEMES)}")
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "ticker", _normalize_token(self.ticker, field="ticker").upper())
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            raise DomainValidationError("valid_from must be earlier than valid_to")
        if self.source is not None:
            object.__setattr__(self, "source", self.source.strip() or None)
        if self.source_version is not None:
            object.__setattr__(self, "source_version", self.source_version.strip() or None)

    def contains(self, as_of: date) -> bool:
        """Return True if ``as_of`` falls in ``[valid_from, valid_to)``."""
        if self.valid_from > as_of:
            return False
        if self.valid_to is None:
            return True
        return as_of < self.valid_to


@dataclass(frozen=True)
class SecurityIdentifier:
    """External identifier attribute (CIK, FIGI, ...). Not the canonical identity."""

    seed_key: str
    id_type: str
    id_value: str
    valid_from: date | None = None
    valid_to: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_key", _normalize_token(self.seed_key, field="seed_key"))
        object.__setattr__(self, "id_type", _normalize_token(self.id_type, field="id_type").upper())
        object.__setattr__(self, "id_value", _normalize_token(self.id_value, field="id_value"))
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise DomainValidationError("valid_from must be earlier than valid_to")


@dataclass(frozen=True)
class Resolution:
    """Listing or vendor resolution. Unknown identity is UNRESOLVED, never a guess."""

    status: str
    security: Security | None = None

    def __post_init__(self) -> None:
        status = self.status.strip().upper()
        if status not in {RESOLUTION_RESOLVED, RESOLUTION_UNRESOLVED}:
            raise DomainValidationError("status must be RESOLVED or UNRESOLVED")
        if status == RESOLUTION_RESOLVED and self.security is None:
            raise DomainValidationError("RESOLVED resolution requires a security")
        if status == RESOLUTION_UNRESOLVED and self.security is not None:
            raise DomainValidationError("UNRESOLVED resolution must not carry a security")
        object.__setattr__(self, "status", status)

    @property
    def is_resolved(self) -> bool:
        return self.status == RESOLUTION_RESOLVED and self.security is not None

    @classmethod
    def resolved(cls, security: Security) -> Resolution:
        return cls(status=RESOLUTION_RESOLVED, security=security)

    @classmethod
    def unresolved(cls) -> Resolution:
        return cls(status=RESOLUTION_UNRESOLVED, security=None)
