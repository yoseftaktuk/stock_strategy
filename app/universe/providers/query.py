"""PostgreSQL-backed universe providers. No network access."""

from collections.abc import Sequence
from datetime import date

from app.database.repositories.interfaces import SP500ConstituentRepository
from app.universe.interface import UniverseProvider
from app.universe.models import ConstituentMembership


class HistoricalSP500UniverseProvider(UniverseProvider):
    """Point-in-time S&P 500 constituents from persisted membership intervals."""

    def __init__(self, repository: SP500ConstituentRepository) -> None:
        self._repository = repository

    def get_symbols(self, as_of: date) -> list[str]:
        return sorted({item.symbol for item in self.get_memberships(as_of)})

    def get_memberships(self, as_of: date) -> Sequence[ConstituentMembership]:
        return self._repository.get_memberships_as_of(as_of)


class CurrentSP500UniverseProvider(UniverseProvider):
    """Currently active constituents for every date.

    Using this provider over a historical window is survivorship-biased: names
    that later left the index never appear, and names that later entered appear
    throughout the past.
    """

    def __init__(self, repository: SP500ConstituentRepository) -> None:
        self._repository = repository

    def get_symbols(self, as_of: date) -> list[str]:
        return sorted({item.symbol for item in self.get_memberships(as_of)})

    def get_memberships(self, as_of: date) -> Sequence[ConstituentMembership]:
        del as_of
        return tuple(
            item for item in self._repository.get_all_memberships() if item.end_date is None
        )
