from decimal import Decimal

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position
from tests.fixtures.portfolios import SAMPLE_PORTFOLIO


@pytest.mark.unit
def test_portfolio_equity() -> None:
    assert SAMPLE_PORTFOLIO.equity == Decimal("51540.00")


@pytest.mark.unit
def test_portfolio_rejects_negative_cash() -> None:
    with pytest.raises(DomainValidationError, match="cash must be non-negative"):
        Portfolio(cash=Decimal("-1.00"))


@pytest.mark.unit
def test_portfolio_equity_with_multiple_positions() -> None:
    portfolio = Portfolio(
        cash=Decimal("1000.00"),
        positions=(
            Position(
                symbol="AAPL",
                quantity=Decimal("2"),
                average_price=Decimal("100.00"),
                market_price=Decimal("110.00"),
            ),
            Position(
                symbol="MSFT",
                quantity=Decimal("1"),
                average_price=Decimal("200.00"),
                market_price=Decimal("250.00"),
            ),
        ),
    )
    assert portfolio.equity == Decimal("1470.00")
