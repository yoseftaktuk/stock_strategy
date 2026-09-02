"""Offline market-data provider for backtests.

Backtests must load bars from PostgreSQL (or injected fixtures). Fetching via
yfinance or any network source during a run is a wiring bug.
"""

from collections.abc import Sequence
from datetime import date

from app.data.exceptions import DataProviderError
from app.data.interface import MarketDataFetchResult
from app.domain.models.market_bar import MarketBar


class OfflineMarketDataProvider:
    """Rejects fetch/get so a backtest cannot accidentally download prices."""

    def get_history(self, symbol: str, start: date, end: date) -> Sequence[MarketBar]:
        del start, end
        raise DataProviderError(
            "Backtest must not fetch market data from the network",
            symbol=symbol,
            source="offline",
        )

    def fetch_history(self, symbol: str, start: date, end: date) -> MarketDataFetchResult:
        del start, end
        raise DataProviderError(
            "Backtest must not fetch market data from the network",
            symbol=symbol,
            source="offline",
        )
