import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.stock import Stock


@pytest.mark.unit
def test_stock_valid_construction() -> None:
    stock = Stock(symbol="aapl", exchange="nasdaq", currency="usd")
    assert stock.symbol == "AAPL"
    assert stock.exchange == "NASDAQ"
    assert stock.currency == "USD"


@pytest.mark.unit
def test_stock_empty_symbol_raises() -> None:
    with pytest.raises(DomainValidationError, match="symbol must not be empty"):
        Stock(symbol="", exchange="NASDAQ", currency="USD")


@pytest.mark.unit
def test_stock_equality() -> None:
    left = Stock(symbol="AAPL", exchange="NASDAQ", currency="USD")
    right = Stock(symbol="AAPL", exchange="NASDAQ", currency="USD")
    assert left == right
