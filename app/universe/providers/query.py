"""PostgreSQL-backed universe providers. No network access."""

from datetime import date

from app.database.repositories.interfaces import SP500ConstituentRepository
from app.universe.interface import UniverseProvider


class HistoricalSP500UniverseProvider(UniverseProvider):
    """Point-in-time S&P 500 constituents from persisted membership intervals."""

    def __init__(self, repository: SP500ConstituentRepository) -> None:
        self._repository = repository

    def get_symbols(self, as_of: date) -> list[str]:
        memberships = self._repository.get_memberships_as_of(as_of)
        return sorted({item.symbol for item in memberships})


class CurrentSP500UniverseProvider(UniverseProvider):
    """Currently active constituents for every date.

    Using this provider over a historical window is survivorship-biased: names
    that later left the index never appear, and names that later entered appear
    throughout the past.
    """

    def __init__(self, repository: SP500ConstituentRepository) -> None:
        self._repository = repository

    def get_symbols(self, as_of: date) -> list[str]:
        del as_of
        memberships = self._repository.get_all_memberships()
        return sorted({item.symbol for item in memberships if item.end_date is None})
