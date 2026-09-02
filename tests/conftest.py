import pytest

from tests.fixtures.market_data import SAMPLE_BAR
from tests.fixtures.portfolios import SAMPLE_PORTFOLIO, SAMPLE_POSITION
from tests.fixtures.stocks import SAMPLE_STOCK


@pytest.fixture
def sample_stock():
    return SAMPLE_STOCK


@pytest.fixture
def sample_bar():
    return SAMPLE_BAR


@pytest.fixture
def sample_position():
    return SAMPLE_POSITION


@pytest.fixture
def sample_portfolio():
    return SAMPLE_PORTFOLIO
