from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.backtest.identity_attach import occupancy_by_ticker
from app.broker.simulated import SimulatedBroker
from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityRef
from app.domain.models.listing import Listing
from app.domain.models.order import Order
from app.security_master.identity_resolver import catalog_security_id
from tests.fixtures.universe import membership

UTC = timezone.utc
SESSION = datetime(2024, 6, 3, 9, 30, tzinfo=UTC)
BLOCK = catalog_security_id("block-inc-class-a")
SPECTRA = catalog_security_id("spectra-energy")
SEA = catalog_security_id("sea-limited")


def _broker() -> SimulatedBroker:
    broker = SimulatedBroker(
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
    )
    broker.connect()
    return broker


def _resolved(
    ticker: str,
    security_id: str,
    valid_from: date,
    valid_to: date | None = None,
) -> IdentityRef:
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


def _order(symbol: str, quantity: Decimal, identity: IdentityRef, *, client_order_id: str) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=client_order_id,
        identity=identity,
    )


@pytest.mark.backtest
def test_mtm_unvalued_uses_execution_ticker_not_booking_key() -> None:
    broker = _broker()
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    broker.set_market_prices({"SQ": Decimal("100")}, SESSION)
    broker.submit_order(_order("SQ", Decimal("10"), sq, client_order_id="open-sq"))
    broker.retarget_listings({sq.position_key_value: ("XYZ", xyz)})
    broker.mark_to_market({"XYZ": Decimal("130")}, unvalued={"SQ"})
    valued = broker.get_positions()[0]
    assert valued.valued is True
    assert valued.market_price == Decimal("130")
    assert valued.position_key == sq.position_key_value
    broker.mark_to_market({"XYZ": Decimal("130")}, unvalued={"XYZ"})
    assert broker.get_positions()[0].valued is False
    assert broker.get_positions()[0].position_key == sq.position_key_value


@pytest.mark.backtest
def test_liquidate_at_without_booking_key_refuses_ambiguous_ticker() -> None:
    broker = _broker()
    spectra = _resolved("SE", SPECTRA, date(2007, 1, 3), date(2017, 2, 27))
    sea = _resolved("SE", SEA, date(2017, 10, 20))
    broker.set_market_prices({"SE": Decimal("50")}, SESSION)
    broker.submit_order(_order("SE", Decimal("8"), spectra, client_order_id="spectra"))
    broker.submit_order(_order("SE", Decimal("3"), sea, client_order_id="sea"))
    filled = broker.liquidate_at("SE", Decimal("50"), SESSION, client_order_id="ambiguous-se")
    assert filled is None
    assert len(broker.get_positions()) == 2
    closed = broker.liquidate_at(
        "SE",
        Decimal("50"),
        SESSION,
        client_order_id="term-spectra",
        booking_key=spectra.position_key_value,
    )
    assert closed is not None
    assert closed.status == OrderStatus.FILLED
    remaining = broker.get_positions()
    assert len(remaining) == 1
    assert remaining[0].position_key == sea.position_key_value
    assert remaining[0].identity is sea


@pytest.mark.backtest
def test_duplicate_as_of_occupancy_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="duplicate PIT occupancy"):
        occupancy_by_ticker(
            (
                membership("SE", date(2007, 1, 3), date(2017, 2, 27)),
                membership("SE", date(2016, 1, 1), date(2018, 1, 1)),
            )
        )
