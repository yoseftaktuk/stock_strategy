"""Listing ticker → vendor market-data symbol resolution.

Does not guess identities. UNRESOLVED listings fetch the listing ticker as-is.
Resolved listings also fetch catalog yahoo symbols that overlap the window.
The listing ticker is always included so identity-mismatch series (HAR) still load.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.data.validation import normalize_symbol
from app.domain.models.security import SCHEME_LISTING, SCHEME_YAHOO, SecurityTicker
from app.security_master.interface import SecurityMaster


def vendor_fetch_symbols(
    master: SecurityMaster | None,
    listing_ticker: str,
    start: date,
    end: date,
) -> tuple[str, ...]:
    """Return vendor symbols to load for a PIT listing ticker over ``[start, end]``.

    Inclusive on both ends. The listing ticker is always first so callers can
    fall back to the ticker-row path when no yahoo mapping exists.
    """
    listing = normalize_symbol(listing_ticker)
    if not listing:
        return ()
    if master is None:
        return (listing,)
    names: list[str] = [listing]
    seen = {listing}
    seed_keys = _listing_seed_keys(master, listing, start, end)
    for item in _catalog_tickers(master):
        if item.scheme != SCHEME_YAHOO or item.seed_key not in seed_keys:
            continue
        if not _overlaps_inclusive(item.valid_from, item.valid_to, start, end):
            continue
        if item.ticker not in seen:
            seen.add(item.ticker)
            names.append(item.ticker)
    return tuple(names)


def preferred_vendor_symbol(
    master: SecurityMaster | None,
    listing_ticker: str,
    start: date,
    end: date,
) -> str:
    """Return the yahoo symbol when mapped, else the listing ticker."""
    names = vendor_fetch_symbols(master, listing_ticker, start, end)
    if len(names) > 1:
        return names[1]
    return names[0] if names else normalize_symbol(listing_ticker)


def _listing_seed_keys(
    master: SecurityMaster,
    listing: str,
    start: date,
    end: date,
) -> set[str]:
    keys: set[str] = set()
    for item in _catalog_tickers(master):
        if item.scheme != SCHEME_LISTING or item.ticker != listing:
            continue
        if _overlaps_inclusive(item.valid_from, item.valid_to, start, end):
            keys.add(item.seed_key)
    if keys:
        return keys
    resolved = master.resolve_security(listing, start)
    if resolved.is_resolved and resolved.security is not None:
        keys.add(resolved.security.seed_key)
    return keys


def _catalog_tickers(master: SecurityMaster) -> Sequence[SecurityTicker]:
    tickers = getattr(master, "tickers", None)
    if callable(tickers):
        return tuple(tickers())
    return ()


def _overlaps_inclusive(
    valid_from: date,
    valid_to: date | None,
    start: date,
    end: date,
) -> bool:
    if valid_from > end:
        return False
    if valid_to is None:
        return True
    return start < valid_to
