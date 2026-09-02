from decimal import Decimal

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.position import Position
from tests.fixtures.portfolios import SAMPLE_POSITION


@pytest.mark.unit
def test_position_market_value() -> None:
    assert SAMPLE_POSITION.market_value == Decimal("1540.00")


@pytest.mark.unit
def test_unvalued_position_excludes_market_value() -> None:
    position = Position(
        symbol="AAPL",
        quantity=Decimal("10"),
        average_price=Decimal("150.00"),
        market_price=Decimal("154.00"),
        valued=False,
    )
    assert position.market_value == Decimal("0")
    assert position.market_price == Decimal("154.00")


@pytest.mark.unit
def test_position_rejects_negative_quantity() -> None:
    with pytest.raises(DomainValidationError, match="quantity must be non-negative"):
        Position(
            symbol="AAPL",
            quantity=Decimal("-1"),
            average_price=Decimal("150.00"),
            market_price=Decimal("154.00"),
        )


@pytest.mark.unit
def test_position_rejects_negative_price() -> None:
    with pytest.raises(DomainValidationError, match="market_price must be non-negative"):
        Position(
            symbol="AAPL",
            quantity=Decimal("10"),
            average_price=Decimal("150.00"),
            market_price=Decimal("-1.00"),
        )
