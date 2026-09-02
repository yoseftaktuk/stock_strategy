from app.database.repositories.interfaces import SP500ConstituentRepository
from app.universe.exceptions import UniverseProviderError
from app.universe.interface import UniverseProvider
from app.universe.providers.query import CurrentSP500UniverseProvider, HistoricalSP500UniverseProvider

HISTORICAL_SP500 = "historical_sp500"
CURRENT = "current"
UNIVERSE_CHOICES = (HISTORICAL_SP500, CURRENT)


def create_universe_provider(kind: str, repository: SP500ConstituentRepository) -> UniverseProvider:
    name = kind.strip().lower()
    if name == HISTORICAL_SP500:
        return HistoricalSP500UniverseProvider(repository)
    if name == CURRENT:
        return CurrentSP500UniverseProvider(repository)
    raise UniverseProviderError(
        f"Unsupported universe: {kind}. Expected one of: {', '.join(UNIVERSE_CHOICES)}"
    )
