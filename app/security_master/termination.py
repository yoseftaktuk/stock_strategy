"""Known listing termination versus missing market data.

A series with no further bars is not automatically an economic exit. Only a
resolved DELISTED listing (acquisition, delisting, or other listing end) is a
known termination. UNRESOLVED or ACTIVE names are data-quality / identity
problems, not invented liquidations.

PIT index removal is not termination: a name that left the S&P 500 but still
trades is sold at the next rebalance open when a price exists.
"""

from __future__ import annotations

from datetime import date

from app.data.validation import normalize_symbol
from app.domain.models.security import SCHEME_LISTING, STATUS_DELISTED
from app.security_master.interface import SecurityMaster


def is_known_listing_termination(
    master: SecurityMaster | None,
    ticker: str,
    *,
    last_bar: date,
    session: date,
) -> bool:
    """Return True when ``ticker`` has a known listing end before ``session``.

    ``last_bar < session`` means the loaded tape has already stopped. That is
    necessary but not sufficient. The Security Master must resolve the listing
    as DELISTED. Last tape on an exclusive ``valid_to`` date still counts.
    """
    if master is None or last_bar >= session:
        return False
    name = normalize_symbol(ticker)
    if not name:
        return False

    resolved = master.resolve_security(name, last_bar)
    if resolved.is_resolved and resolved.security is not None:
        return resolved.security.status == STATUS_DELISTED

    for item in master.tickers():
        if item.scheme != SCHEME_LISTING or item.ticker != name:
            continue
        if item.valid_to is None:
            continue
        if item.valid_from <= last_bar <= item.valid_to:
            security = master.get_security(item.seed_key)
            if security is not None and security.status == STATUS_DELISTED:
                return True
    return False
