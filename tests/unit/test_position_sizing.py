from decimal import Decimal

import pytest

from tests.fixtures.portfolios import SAMPLE_PORTFOLIO, SAMPLE_POSITION


@pytest.mark.unit
def test_position_market_value() -> None:
    assert SAMPLE_POSITION.market_value == Decimal("1540.00")


@pytest.mark.unit
def test_portfolio_equity() -> None:
    assert SAMPLE_PORTFOLIO.equity == Decimal("51540.00")
