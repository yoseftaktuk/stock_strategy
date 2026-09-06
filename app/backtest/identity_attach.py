"""Attach a once-resolved IdentityRef onto strategy signals.

Resolution happens here (PIT ticker + as_of + occupancy), then identity is
copied through TargetPosition → Order → Fill → Position. Layers below must
not call the resolver again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date

from app.domain.exceptions import DomainValidationError
from app.domain.identity import IdentityResolver
from app.domain.models.signal import MomentumSignal
from app.universe.models import ConstituentMembership


def occupancy_by_ticker(
    memberships: Sequence[ConstituentMembership],
) -> dict[str, ConstituentMembership]:
    """Map PIT ticker → occupancy for one as-of date.

    Ticker is the occupancy lookup at resolution time, not a booking key.
    Two occupancies of the same ticker on one as-of date cannot share a slot.
    """
    mapping: dict[str, ConstituentMembership] = {}
    for item in memberships:
        if item.symbol in mapping:
            raise DomainValidationError(
                f"duplicate PIT occupancy for ticker={item.symbol}; "
                "ticker is not a recycle-safe identity key"
            )
        mapping[item.symbol] = item
    return mapping


def attach_signal_identities(
    signals: Sequence[MomentumSignal],
    resolver: IdentityResolver,
    as_of: date,
    occupancy: Mapping[str, ConstituentMembership] | None = None,
) -> list[MomentumSignal]:
    """Copy ``resolve(ticker, as_of, occupancy=...)`` onto each signal."""
    occupancy_map = occupancy or {}
    attached: list[MomentumSignal] = []
    for signal in signals:
        membership = occupancy_map.get(signal.symbol)
        identity = resolver.resolve(
            signal.symbol,
            as_of,
            occupancy_from=None if membership is None else membership.start_date,
            occupancy_to=None if membership is None else membership.end_date,
        )
        attached.append(replace(signal, identity=identity))
    return attached
