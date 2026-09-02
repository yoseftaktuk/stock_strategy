"""In-memory universe provider for tests and backtest snapshots.

Backtests snapshot memberships from PostgreSQL, then query this provider so
execution does not perform network or database I/O for universe data.
"""

from collections.abc import Sequence
from datetime import date

from app.universe.interface import UniverseProvider
from app.universe.models import ConstituentMembership


class InMemoryUniverseProvider(UniverseProvider):
    """Point-in-time or current-only membership over a fixed interval list."""

    def __init__(
        self,
        memberships: Sequence[ConstituentMembership],
        *,
        current_only: bool = False,
    ) -> None:
        self._memberships = tuple(memberships)
        self._current_only = current_only

    def get_symbols(self, as_of: date) -> list[str]:
        if self._current_only:
            selected = [item.symbol for item in self._memberships if item.end_date is None]
        else:
            selected = [item.symbol for item in self._memberships if item.contains(as_of)]
        return sorted(set(selected))
