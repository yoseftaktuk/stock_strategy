from datetime import date

import pytest

from app.universe.memory import InMemoryUniverseProvider
from app.universe.coverage import missing_market_data_symbols
from tests.fixtures.universe import survivorship_memberships


@pytest.mark.unit
def test_missing_price_data_is_reported() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    universe = provider.get_symbols(date(2015, 1, 2))
    assert universe == ["AAA", "BBB", "CCC"]

    market_data = {"AAA": [object()], "CCC": []}
    missing = missing_market_data_symbols(universe, market_data)
    assert missing == ["BBB", "CCC"]
    assert "AAA" not in missing
    assert provider.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]
