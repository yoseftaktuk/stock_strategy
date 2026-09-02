from pathlib import Path

import pytest

from app.config.settings import Settings
from app.data.exceptions import DataProviderError
from app.data.factory import create_market_data_provider
from app.data.providers.csv import CSVMarketDataProvider
from app.data.providers.historical import HistoricalMarketDataProvider
from app.data.providers.ibkr import IBKRMarketDataProvider


@pytest.mark.unit
def test_factory_creates_csv_provider(tmp_path: Path) -> None:
    settings = Settings(data_provider="CSV", csv_data_path=str(tmp_path))
    provider = create_market_data_provider(settings)
    assert isinstance(provider, CSVMarketDataProvider)


@pytest.mark.unit
def test_factory_creates_historical_provider(tmp_path: Path) -> None:
    settings = Settings(data_provider="HISTORICAL", csv_data_path=str(tmp_path))
    provider = create_market_data_provider(settings)
    assert isinstance(provider, HistoricalMarketDataProvider)


@pytest.mark.unit
def test_factory_provider_override(tmp_path: Path) -> None:
    settings = Settings(data_provider="CSV", csv_data_path=str(tmp_path))
    provider = create_market_data_provider(settings, provider_name="historical")
    assert isinstance(provider, HistoricalMarketDataProvider)


@pytest.mark.unit
def test_factory_creates_ibkr_stub() -> None:
    settings = Settings(data_provider="IBKR")
    provider = create_market_data_provider(settings)
    assert isinstance(provider, IBKRMarketDataProvider)


@pytest.mark.unit
def test_factory_rejects_unknown_provider() -> None:
    settings = Settings(data_provider="POLYGON")
    with pytest.raises(DataProviderError, match="Unsupported data provider"):
        create_market_data_provider(settings)
