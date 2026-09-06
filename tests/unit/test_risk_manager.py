from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import OrderSide, OrderType
from app.domain.models.identity import IdentityRef
from app.domain.models.listing import Listing
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position
from app.risk.risk_manager import RiskManager
from app.security_master.identity_resolver import catalog_security_id
from tests.fixtures.portfolios import SAMPLE_PORTFOLIO

BLOCK = catalog_security_id("block-inc-class-a")
SPECTRA = catalog_security_id("spectra-energy")
SEA = catalog_security_id("sea-limited")


def _resolved(ticker: str, security_id: str, valid_from: date, valid_to: date | None = None) -> IdentityRef:
    return IdentityRef.resolved(
        security_id=security_id,
        listing=Listing(
            ticker=ticker,
            valid_from=valid_from,
            valid_to=valid_to,
            security_id=security_id,
        ),
        ticker_as_of=ticker,
    )


def _sell(symbol: str, quantity: Decimal, identity: IdentityRef | None = None) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=f"sell-{symbol}-{quantity}",
        identity=identity,
    )


@pytest.mark.unit
def test_risk_manager_validate_returns_true() -> None:
    risk_manager = RiskManager()
    order = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="test-001",
    )
    assert risk_manager.validate(order, SAMPLE_PORTFOLIO) is True


@pytest.mark.unit
def test_risk_manager_rejects_short_sale() -> None:
    risk_manager = RiskManager()
    order = Order(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=Decimal("1000"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="test-short",
    )
    assert risk_manager.validate(order, SAMPLE_PORTFOLIO) is False


@pytest.mark.unit
def test_risk_manager_allows_rename_sell_by_position_key() -> None:
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    portfolio = Portfolio(
        cash=Decimal("90000"),
        positions=(Position("SQ", Decimal("10"), Decimal("100"), Decimal("100"), identity=sq),),
    )
    assert RiskManager().validate(_sell("XYZ", Decimal("10"), xyz), portfolio) is True
    assert RiskManager().validate(_sell("XYZ", Decimal("11"), xyz), portfolio) is False


@pytest.mark.unit
def test_risk_manager_does_not_merge_recycled_ticker_quantity() -> None:
    spectra = _resolved("SE", SPECTRA, date(2007, 1, 3), date(2017, 2, 27))
    sea = _resolved("SE", SEA, date(2017, 10, 20))
    portfolio = Portfolio(
        cash=Decimal("96000"),
        positions=(Position("SE", Decimal("8"), Decimal("50"), Decimal("50"), identity=spectra),),
    )
    assert RiskManager().validate(_sell("SE", Decimal("8"), spectra), portfolio) is True
    assert RiskManager().validate(_sell("SE", Decimal("1"), sea), portfolio) is False
