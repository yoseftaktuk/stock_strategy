"""Point-in-time equity universe abstractions.

The default historical S&P 500 source (fja05680/sp500) is a public reconstruction,
not an official S&P Dow Jones Indices data feed. Membership queries are
survivorship-aware and point-in-time; they do not make a backtest fully bias-free.

Import ``UniverseService`` from ``app.universe.service`` to avoid a package-level
import cycle with the database repository protocols.
"""

from app.universe.coverage import missing_market_data_symbols
from app.universe.interface import UniverseProvider
from app.universe.models import ConstituentMembership

__all__ = [
    "ConstituentMembership",
    "UniverseProvider",
    "missing_market_data_symbols",
]
