"""Catalog adapter for the domain IdentityResolver contract.

Uses existing Security Master listing intervals. Does not mint securities for
unknown PIT tickers. Vendor (Yahoo) symbol rows are not listings.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityRef
from app.domain.models.listing import Listing
from app.domain.models.security import SCHEME_LISTING
from app.security_master.exceptions import SecurityMasterValidationError
from app.security_master.interface import SecurityMaster

CATALOG_SECURITY_ID_PREFIX = "catalog:"


def catalog_security_id(seed_key: str, *, db_id: int | None = None) -> str:
    """Catalog-local runtime id. Never a ticker and never a vendor asset id."""
    if db_id is not None:
        return str(db_id)
    return f"{CATALOG_SECURITY_ID_PREFIX}{seed_key}"


def _effective_end(listing: Listing) -> date:
    return listing.valid_to if listing.valid_to is not None else date.max


def _occupancy_key(listing: Listing) -> tuple[str, str]:
    exchange = listing.exchange or ""
    return (exchange, listing.ticker)


def listings_overlap(left: Listing, right: Listing) -> bool:
    if _occupancy_key(left) != _occupancy_key(right):
        return False
    return left.valid_from < _effective_end(right) and right.valid_from < _effective_end(left)


class CatalogIdentityResolver:
    """``resolve(ticker, as_of)`` against catalog listings plus optional extras."""

    def __init__(
        self,
        master: SecurityMaster | None = None,
        listings: Sequence[Listing] = (),
    ) -> None:
        derived = tuple(_listings_from_master(master)) if master is not None else ()
        combined = (*derived, *tuple(listings))
        _validate_listing_occupancies(combined)
        self._master = master
        grouped: dict[str, list[Listing]] = defaultdict(list)
        for listing in combined:
            grouped[listing.ticker].append(listing)
        self._by_ticker = {
            ticker: tuple(sorted(values, key=lambda item: item.valid_from))
            for ticker, values in grouped.items()
        }

    @classmethod
    def from_catalog(cls, master: SecurityMaster) -> CatalogIdentityResolver:
        return cls(master)

    def security_id_for_seed_key(self, seed_key: str) -> str | None:
        """Return the catalog-local security_id for an authored seed_key, if present."""
        if self._master is None:
            return None
        security = self._master.get_security(seed_key)
        if security is None:
            return None
        return catalog_security_id(security.seed_key, db_id=security.security_id)

    def resolve(
        self,
        ticker: str,
        as_of: date,
        *,
        occupancy_from: date | None = None,
        occupancy_to: date | None = None,
    ) -> IdentityRef:
        normalized = ticker.strip().upper()
        if not normalized:
            raise DomainValidationError("ticker must not be empty")
        matches = [
            listing
            for listing in self._by_ticker.get(normalized, ())
            if listing.contains(as_of)
        ]
        if len(matches) == 1:
            listing = matches[0]
            if listing.security_id is not None:
                return IdentityRef.resolved(
                    security_id=listing.security_id,
                    listing=listing,
                    ticker_as_of=normalized,
                )
            return IdentityRef.unresolved(listing=listing, ticker_as_of=normalized)
        if occupancy_from is not None:
            return IdentityRef.unresolved(
                listing=Listing(
                    ticker=normalized,
                    valid_from=occupancy_from,
                    valid_to=occupancy_to,
                    security_id=None,
                ),
                ticker_as_of=normalized,
            )
        return IdentityRef.unresolved(
            listing=Listing.unknown_occupancy(normalized, as_of),
            ticker_as_of=normalized,
        )


def _listings_from_master(master: SecurityMaster) -> list[Listing]:
    listings: list[Listing] = []
    for ticker in master.tickers():
        if ticker.scheme != SCHEME_LISTING:
            continue
        security = master.get_security(ticker.seed_key)
        security_id = None
        if security is not None:
            security_id = catalog_security_id(security.seed_key, db_id=security.security_id)
        listings.append(
            Listing(
                ticker=ticker.ticker,
                valid_from=ticker.valid_from,
                valid_to=ticker.valid_to,
                security_id=security_id,
            )
        )
    return listings


def _validate_listing_occupancies(listings: Sequence[Listing]) -> None:
    by_key: dict[tuple[str, str], list[Listing]] = defaultdict(list)
    for listing in listings:
        by_key[_occupancy_key(listing)].append(listing)
    overlapping: list[str] = []
    for (_exchange, ticker), periods in by_key.items():
        ordered = sorted(periods, key=lambda item: (item.valid_from, _effective_end(item)))
        for index, current in enumerate(ordered):
            for other in ordered[index + 1 :]:
                if listings_overlap(current, other):
                    overlapping.append(
                        f"{ticker} {current.valid_from.isoformat()} {other.valid_from.isoformat()}"
                    )
    if overlapping:
        raise SecurityMasterValidationError(
            "overlapping listing occupancies",
            issues=tuple(overlapping),
        )
