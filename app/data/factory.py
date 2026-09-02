from pathlib import Path

from app.config.settings import Settings
from app.data.exceptions import DataProviderError
from app.data.interface import MarketDataProvider


def create_market_data_provider(
    settings: Settings,
    *,
    provider_name: str | None = None,
) -> MarketDataProvider:
    name = (provider_name or settings.data_provider).strip().upper()
    if name == "CSV":
        from app.data.providers.csv import CSVMarketDataProvider

        return CSVMarketDataProvider(Path(settings.csv_data_path))
    if name == "HISTORICAL":
        from app.data.providers.historical import HistoricalMarketDataProvider

        return HistoricalMarketDataProvider(cache_dir=Path(settings.csv_data_path))
    if name == "IBKR":
        from app.data.providers.ibkr import IBKRMarketDataProvider

        return IBKRMarketDataProvider()
    raise DataProviderError(
        f"Unsupported data provider: {provider_name or settings.data_provider}",
        source=provider_name or settings.data_provider,
    )
