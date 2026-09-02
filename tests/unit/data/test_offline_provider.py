from datetime import date

import pytest

from app.data.exceptions import DataProviderError
from app.data.providers.offline import OfflineMarketDataProvider


@pytest.mark.unit
def test_offline_provider_rejects_network_fetch() -> None:
    provider = OfflineMarketDataProvider()
    with pytest.raises(DataProviderError, match="must not fetch"):
        provider.fetch_history("AAPL", date(2015, 1, 1), date(2015, 12, 31))
    with pytest.raises(DataProviderError, match="must not fetch"):
        provider.get_history("AAPL", date(2015, 1, 1), date(2015, 12, 31))
