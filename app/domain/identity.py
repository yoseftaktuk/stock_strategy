"""Domain contract for as-of listing identity resolution.

Ticker recycle is why ``as_of`` is required. Implementations must not mint a
security_id from a ticker, vendor asset id, or hash of either.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.domain.models.identity import IdentityRef, PositionKey, position_key_for
from app.domain.models.listing import Listing

__all__ = [
    "IdentityRef",
    "IdentityResolver",
    "Listing",
    "PositionKey",
    "position_key_for",
]


class IdentityResolver(Protocol):
    def resolve(
        self,
        ticker: str,
        as_of: date,
        *,
        occupancy_from: date | None = None,
        occupancy_to: date | None = None,
    ) -> IdentityRef:
        """Return the identity ``ticker`` represented on ``as_of``.

        RESOLVED: ``security_id`` is the economic instrument. Position key is
        that id so a rename stays one position.
        UNRESOLVED: ``security_id`` is None. Position key is listing occupancy.
        When the catalog has no listing, ``occupancy_from`` / ``occupancy_to``
        (PIT membership) form the listing identity. Ticker+as_of alone is not
        a recycle-safe fallback.
        """
        ...
