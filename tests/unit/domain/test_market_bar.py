from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.market_bar import MarketBar
from tests.fixtures.market_data import SAMPLE_BAR, UTC


@pytest.mark.unit
def test_market_bar_valid_construction() -> None:
    assert SAMPLE_BAR.symbol == "AAPL"
    assert SAMPLE_BAR.close == Decimal("154.00")


@pytest.mark.unit
def test_market_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 16, 0),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            adjusted_close=Decimal("154.00"),
            volume=1_000_000,
        )


@pytest.mark.unit
def test_market_bar_rejects_invalid_ohlc() -> None:
    with pytest.raises(DomainValidationError, match="high must be >= low"):
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 16, 0, tzinfo=UTC),
            open=Decimal("150.00"),
            high=Decimal("140.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            adjusted_close=Decimal("154.00"),
            volume=1_000_000,
        )


@pytest.mark.unit
def test_market_bar_rejects_negative_volume() -> None:
    with pytest.raises(DomainValidationError, match="volume must be non-negative"):
        MarketBar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 16, 0, tzinfo=UTC),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            adjusted_close=Decimal("154.00"),
            volume=-1,
        )
