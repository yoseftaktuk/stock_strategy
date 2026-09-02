"""Security-identity assessment for loaded market-data series.

PIT membership is independent of identity. A series can fail identity without
being removed from the universe. Callers must not use ticker blacklists.

When a vendor mapping exists, bars outside that mapping are dropped (no
predecessor continuity unless the catalog records it). Listing identity is
resolved from the PIT dict key; vendor identity is resolved from ``bar.symbol``
so a proven ticker-change alias can be joined. When a listing ticker resolves
to a known security that the vendor series does not map to, the entire series
is identity_mismatch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.models.market_bar import MarketBar
from app.security_master.interface import SecurityMaster

REASON_IDENTITY_MISMATCH = "identity_mismatch"


@dataclass(frozen=True)
class IdentitySeriesQuality:
    symbol: str
    bars: tuple[MarketBar, ...]
    usable: bool
    reason: str | None = None


def apply_identity(
    market_data: Mapping[str, Sequence[MarketBar]],
    master: SecurityMaster | None,
) -> tuple[dict[str, tuple[MarketBar, ...]], dict[str, str]]:
    """Clip vendor-invalid bars and flag identity-mismatched series.

    Empty ``master`` or ``None`` leaves series unchanged (identity-unproven).
    """
    if master is None:
        return (
            {symbol: tuple(bars) for symbol, bars in market_data.items()},
            {},
        )
    clipped: dict[str, tuple[MarketBar, ...]] = {}
    unusable: dict[str, str] = {}
    for symbol, bars in market_data.items():
        assessment = assess_identity_series(symbol, bars, master)
        clipped[symbol] = assessment.bars
        if not assessment.usable and assessment.reason is not None:
            unusable[symbol] = assessment.reason
    return clipped, unusable


def assess_identity_series(
    symbol: str,
    bars: Sequence[MarketBar],
    master: SecurityMaster,
) -> IdentitySeriesQuality:
    """Classify one symbol series against the Security Master."""
    if not bars:
        return IdentitySeriesQuality(symbol=symbol, bars=(), usable=True, reason=None)

    mismatch = False
    for bar in bars:
        as_of = bar.timestamp.date()
        listing = master.resolve_security(symbol, as_of)
        vendor = master.resolve_market_data_symbol(bar.symbol, as_of)
        if listing.is_resolved:
            listing_security = listing.security
            vendor_security = vendor.security if vendor.is_resolved else None
            if listing_security is None:
                continue
            if vendor_security is None or vendor_security.seed_key != listing_security.seed_key:
                mismatch = True
                break

    if mismatch:
        return IdentitySeriesQuality(
            symbol=symbol,
            bars=tuple(bars),
            usable=False,
            reason=REASON_IDENTITY_MISMATCH,
        )

    clip_names = {symbol, *(bar.symbol for bar in bars)}
    if any(master.has_vendor_mapping(name) for name in clip_names):
        kept = tuple(
            bar
            for bar in bars
            if master.resolve_market_data_symbol(
                bar.symbol, bar.timestamp.date()
            ).is_resolved
        )
        return IdentitySeriesQuality(symbol=symbol, bars=kept, usable=True, reason=None)

    return IdentitySeriesQuality(symbol=symbol, bars=tuple(bars), usable=True, reason=None)


def identity_unusable_symbols(
    market_data: Mapping[str, Sequence[MarketBar]],
    master: SecurityMaster | None,
) -> dict[str, str]:
    """Return symbol → reason for series that fail identity checks."""
    _, unusable = apply_identity(market_data, master)
    return unusable
