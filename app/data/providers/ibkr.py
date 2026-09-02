from collections.abc import Sequence
from datetime import date

from app.data.interface import MarketDataFetchResult
from app.domain.models.market_bar import MarketBar

_NOT_IMPLEMENTED = "IBKR market data integration not implemented"


class IBKRMarketDataProvider:
    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[MarketBar]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def fetch_history(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> MarketDataFetchResult:
        raise NotImplementedError(_NOT_IMPLEMENTED)
