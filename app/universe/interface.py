"""Universe provider abstraction.

Strategy and backtest code should depend on this interface, not on a specific
index implementation (S&P 500, Nasdaq 100, Russell, custom, or commercial).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from app.universe.models import ConstituentMembership


class UniverseProvider(ABC):
    """Return eligible symbols as of a calendar date without looking ahead."""

    @abstractmethod
    def get_symbols(self, as_of: date) -> list[str]:
        """Return sorted unique symbols that were universe members on ``as_of``.

        Membership uses the half-open interval ``[start_date, end_date)``.
        Implementations must not use future membership events to answer
        historical queries.
        """

    def get_memberships(self, as_of: date) -> Sequence[ConstituentMembership]:
        """Return PIT occupancy rows covering ``as_of``, if the provider stores them.

        Default is empty: explicit ticker lists have no occupancy evidence.
        """
        del as_of
        return ()
