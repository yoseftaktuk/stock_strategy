from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.application.order_service import OrderService
from app.backtest.export import fill_row
from app.broker.simulated import SimulatedBroker
from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.models.identity import IdentityRef, position_key_for
from app.domain.models.listing import Listing
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position
from app.domain.models.target import TargetPortfolio, TargetPosition
from app.security_master.identity_resolver import catalog_security_id
from app.security_master.seed import load_known_identities_catalog

UTC = timezone.utc
SESSION = datetime(2024, 6, 3, 9, 30, tzinfo=UTC)
BLOCK = catalog_security_id("block-inc-class-a")
SPECTRA = catalog_security_id("spectra-energy")
SEA = catalog_security_id("sea-limited")
EXPRESS = catalog_security_id("express-scripts")


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


def _unresolved(ticker: str, valid_from: date, valid_to: date | None = None) -> IdentityRef:
    return IdentityRef.unresolved(
        listing=Listing(ticker=ticker, valid_from=valid_from, valid_to=valid_to),
        ticker_as_of=ticker,
    )


def _order(
    symbol: str,
    quantity: Decimal,
    identity: IdentityRef,
    *,
    side: OrderSide = OrderSide.BUY,
    client_order_id: str = "order-1",
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=client_order_id,
        identity=identity,
    )


@pytest.mark.backtest
def test_rename_sq_to_xyz_keeps_one_position() -> None:
    broker = _broker()
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    broker.set_market_prices({"SQ": Decimal("100")}, SESSION)
    broker.submit_order(_order("SQ", Decimal("10"), sq, client_order_id="open-sq"))
    broker.set_market_prices({"XYZ": Decimal("100")}, SESSION)
    filled = broker.submit_order(_order("XYZ", Decimal("5"), xyz, client_order_id="add-xyz"))
    assert filled.status == OrderStatus.FILLED
    positions = broker.get_positions()
    assert len(positions) == 1
    position = positions[0]
    assert position.position_key == f"security:{BLOCK}"
    assert position.security_id == BLOCK
    assert position.symbol == "XYZ"
    assert position.quantity == Decimal("15")
    assert position.average_price == Decimal("100")
    assert position_key_for(position) == position.position_key


@pytest.mark.backtest
def test_recycle_se_opens_two_positions() -> None:
    broker = _broker()
    spectra = _resolved("SE", SPECTRA, date(2007, 1, 3), date(2017, 2, 27))
    sea = _resolved("SE", SEA, date(2017, 10, 20))
    broker.set_market_prices({"SE": Decimal("50")}, SESSION)
    broker.submit_order(_order("SE", Decimal("8"), spectra, client_order_id="spectra"))
    broker.submit_order(_order("SE", Decimal("3"), sea, client_order_id="sea"))
    positions = broker.get_positions()
    assert len(positions) == 2
    keys = {position.position_key for position in positions}
    assert keys == {f"security:{SPECTRA}", f"security:{SEA}"}
    assert all(position.symbol == "SE" for position in positions)
    by_key = {position.position_key: position for position in positions}
    assert by_key[f"security:{SPECTRA}"].quantity == Decimal("8")
    assert by_key[f"security:{SEA}"].quantity == Decimal("3")


@pytest.mark.backtest
def test_unresolved_recycle_uses_distinct_listing_keys() -> None:
    broker = _broker()
    first = _unresolved("SE", date(2007, 1, 3), date(2017, 2, 27))
    second = _unresolved("SE", date(2017, 10, 20))
    assert first.security_id is None and second.security_id is None
    assert first.position_key() != second.position_key()
    broker.set_market_prices({"SE": Decimal("40")}, SESSION)
    broker.submit_order(_order("SE", Decimal("4"), first, client_order_id="listing-a"))
    broker.submit_order(_order("SE", Decimal("6"), second, client_order_id="listing-b"))
    positions = broker.get_positions()
    assert len(positions) == 2
    keys = {position.position_key for position in positions}
    assert keys == {first.position_key_value, second.position_key_value}
    assert all(key.startswith("listing:") for key in keys)


@pytest.mark.backtest
def test_fill_identity_is_preserved_across_rename() -> None:
    broker = _broker()
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    broker.set_market_prices({"SQ": Decimal("100")}, SESSION)
    open_order = _order("SQ", Decimal("10"), sq, client_order_id="open-sq")
    broker.submit_order(open_order)
    broker.set_market_prices({"XYZ": Decimal("110")}, SESSION)
    close_order = _order(
        "XYZ",
        Decimal("10"),
        xyz,
        side=OrderSide.SELL,
        client_order_id="close-xyz",
    )
    filled = broker.submit_order(close_order)
    assert filled.status == OrderStatus.FILLED
    fills = broker.get_fills()
    assert len(fills) == 2
    assert fills[0].identity is open_order.identity
    assert fills[1].identity is close_order.identity
    assert fills[0].security_id == fills[1].security_id == BLOCK
    assert fills[0].position_key == fills[1].position_key == f"security:{BLOCK}"
    assert fills[0].listing_id == sq.listing_id
    assert fills[1].listing_id == xyz.listing_id
    assert fills[0].symbol == "SQ"
    assert fills[1].symbol == "XYZ"
    exported = fill_row(fills[1], close_order)
    assert exported["security_id"] == BLOCK
    assert exported["symbol"] == "XYZ"
    assert exported["position_key"] == f"security:{BLOCK}"
    broker_source = Path("app/broker/simulated.py").read_text(encoding="utf-8")
    assert ".resolve(" not in broker_source


@pytest.mark.backtest
def test_accounting_continuity_across_rename() -> None:
    broker = _broker()
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    broker.set_market_prices({"SQ": Decimal("100")}, SESSION)
    broker.submit_order(_order("SQ", Decimal("10"), sq, client_order_id="open-sq"))
    cash_after_open = broker.get_account().cash
    broker.set_market_prices({"XYZ": Decimal("120")}, SESSION)
    broker.submit_order(_order("XYZ", Decimal("10"), xyz, client_order_id="add-xyz"))
    position = broker.get_positions()[0]
    assert position.quantity == Decimal("20")
    assert position.average_price == Decimal("110")
    assert position.symbol == "XYZ"
    cash_before_sell = broker.get_account().cash
    sold = broker.submit_order(
        _order("XYZ", Decimal("5"), xyz, side=OrderSide.SELL, client_order_id="reduce-xyz")
    )
    assert sold.status == OrderStatus.FILLED
    remaining = broker.get_positions()[0]
    assert remaining.quantity == Decimal("15")
    assert remaining.average_price == Decimal("110")
    assert broker.get_account().cash == cash_before_sell + Decimal("5") * Decimal("120")
    assert broker.winning_trades == 1
    assert cash_after_open == Decimal("100000") - Decimal("1000")


@pytest.mark.backtest
def test_esrx_liquidation_keeps_predecessor_identity() -> None:
    broker = _broker()
    esrx = _resolved("ESRX", EXPRESS, date(2003, 9, 26), date(2018, 12, 21))
    broker.set_market_prices({"ESRX": Decimal("80")}, SESSION)
    broker.submit_order(_order("ESRX", Decimal("7"), esrx, client_order_id="open-esrx"))
    filled = broker.liquidate_at(
        "ESRX",
        Decimal("90"),
        SESSION,
        client_order_id="2018-12-21-TERM-ESRX",
        booking_key=esrx.position_key_value,
    )
    assert filled is not None
    assert filled.status == OrderStatus.FILLED
    assert filled.identity is esrx
    assert filled.security_id == EXPRESS
    assert filled.symbol == "ESRX"
    terminal = broker.get_fills()[-1]
    assert terminal.identity is esrx
    assert terminal.security_id == EXPRESS
    assert terminal.position_key == f"security:{EXPRESS}"
    assert terminal.slippage == Decimal("0")
    assert broker.get_positions() == []
    catalog = load_known_identities_catalog()
    cigna = catalog.get_security("cigna")
    assert cigna is None or terminal.security_id != catalog_security_id("cigna")


@pytest.mark.backtest
def test_order_service_rename_nets_on_position_key() -> None:
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    current = Portfolio(
        cash=Decimal("90000"),
        positions=(Position("SQ", Decimal("100"), Decimal("100"), Decimal("100"), identity=sq),),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("XYZ", Decimal("0.10"), identity=xyz),),
        cash_weight=Decimal("0.90"),
    )
    orders = OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")).create_orders_from_targets(
        current,
        target,
        {"XYZ": Decimal("100")},
        min_trade_value=Decimal("1"),
        as_of=date(2025, 6, 2),
    )
    assert orders == []


@pytest.mark.backtest
def test_order_service_recycle_does_not_merge_same_ticker() -> None:
    spectra = _resolved("SE", SPECTRA, date(2007, 1, 3), date(2017, 2, 27))
    sea = _resolved("SE", SEA, date(2017, 10, 20))
    current = Portfolio(
        cash=Decimal("96000"),
        positions=(Position("SE", Decimal("80"), Decimal("50"), Decimal("50"), identity=spectra),),
    )
    target = TargetPortfolio(
        positions=(TargetPosition("SE", Decimal("0.04"), identity=sea),),
        cash_weight=Decimal("0.96"),
    )
    orders = OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")).create_orders_from_targets(
        current,
        target,
        {"SE": Decimal("50")},
        min_trade_value=Decimal("1"),
        as_of=date(2018, 6, 1),
    )
    assert [order.side for order in orders] == [OrderSide.SELL, OrderSide.BUY]
    assert orders[0].identity is spectra
    assert orders[1].identity is sea
    assert orders[0].quantity == Decimal("80")
    assert orders[0].position_key != orders[1].position_key


@pytest.mark.backtest
def test_retarget_listings_updates_execution_ticker_not_quantity() -> None:
    broker = _broker()
    sq = _resolved("SQ", BLOCK, date(2015, 11, 19), date(2025, 1, 21))
    xyz = _resolved("XYZ", BLOCK, date(2025, 1, 21))
    broker.set_market_prices({"SQ": Decimal("100")}, SESSION)
    broker.submit_order(_order("SQ", Decimal("10"), sq, client_order_id="open-sq"))
    broker.retarget_listings({sq.position_key_value: ("XYZ", xyz)})
    position = broker.get_positions()[0]
    assert position.symbol == "XYZ"
    assert position.quantity == Decimal("10")
    assert position.average_price == Decimal("100")
    assert position.position_key == sq.position_key_value
    broker.mark_to_market({"XYZ": Decimal("130")})
    valued = broker.get_positions()[0]
    assert valued.market_price == Decimal("130")
    assert valued.symbol == "XYZ"
    assert valued.valued is True
