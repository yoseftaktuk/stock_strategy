from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.identity_attach import attach_signal_identities, occupancy_by_ticker
from app.broker.simulated import SimulatedBroker
from app.domain.models.listing import occupancy_listing_id
from app.domain.models.signal import MomentumSignal
from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.identity_resolver import CatalogIdentityResolver, catalog_security_id
from app.security_master.seed import load_known_identities_catalog
from tests.fixtures.universe import membership

UTC = timezone.utc
SESSION = datetime(2024, 6, 3, 14, 30, tzinfo=UTC)


def _signal(symbol: str, as_of: date = date(2024, 6, 3)) -> MomentumSignal:
    return MomentumSignal(
        symbol=symbol,
        date=as_of,
        momentum=Decimal("0.20"),
        rank=1,
        eligible=True,
    )


def _propagate(identity_signals: list[MomentumSignal], *, as_of: date = date(2024, 6, 3)):
    target = PortfolioService().build_target_portfolio(identity_signals)
    broker = SimulatedBroker(initial_capital=Decimal("100000"), commission_rate=Decimal("0"), slippage_bps=Decimal("0"))
    broker.connect()
    prices = {signal.symbol: Decimal("50") for signal in identity_signals}
    broker.set_market_prices(prices, SESSION)
    orders = OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")).create_orders_from_targets(
        broker.get_account(),
        target,
        prices,
        min_trade_value=Decimal("1"),
        as_of=as_of,
    )
    filled = [broker.submit_order(order) for order in orders]
    return target, filled, broker.get_fills(), broker.get_positions()


@pytest.mark.unit
def test_identity_propagates_signal_to_position() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    occupancy = occupancy_by_ticker((membership("SQ", date(2015, 11, 19), date(2025, 1, 21)),))
    signals = attach_signal_identities([_signal("SQ")], resolver, date(2024, 6, 3), occupancy)
    target, orders, fills, positions = _propagate(signals)
    expected_security = catalog_security_id("block-inc-class-a")
    expected_listing = occupancy_listing_id(ticker="SQ", exchange=None, valid_from=date(2015, 11, 19))
    expected_key = f"security:{expected_security}"
    chain = (signals[0], target.positions[0], orders[0], fills[0], positions[0])
    for item in chain:
        assert item.security_id == expected_security
        assert item.listing_id == expected_listing
        assert item.position_key == expected_key
        assert item.identity is signals[0].identity


@pytest.mark.unit
def test_sq_and_xyz_share_security_id_across_listing_change() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    sq = attach_signal_identities(
        [_signal("SQ", date(2024, 6, 3))],
        resolver,
        date(2024, 6, 3),
        occupancy_by_ticker((membership("SQ", date(2015, 11, 19), date(2025, 1, 21)),)),
    )[0]
    xyz = attach_signal_identities(
        [_signal("XYZ", date(2025, 6, 2))],
        resolver,
        date(2025, 6, 2),
        occupancy_by_ticker((membership("XYZ", date(2025, 1, 21)),)),
    )[0]
    assert sq.security_id == xyz.security_id == catalog_security_id("block-inc-class-a")
    assert sq.listing_id != xyz.listing_id
    assert sq.position_key == xyz.position_key
    assert sq.symbol == "SQ" and xyz.symbol == "XYZ"


@pytest.mark.unit
def test_se_recycle_propagates_different_security_ids() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    spectra = attach_signal_identities(
        [_signal("SE", date(2015, 6, 1))],
        resolver,
        date(2015, 6, 1),
        occupancy_by_ticker((membership("SE", date(2007, 1, 3), date(2017, 2, 27)),)),
    )[0]
    sea = attach_signal_identities(
        [_signal("SE", date(2018, 6, 1))],
        resolver,
        date(2018, 6, 1),
        occupancy_by_ticker((membership("SE", date(2017, 10, 20)),)),
    )[0]
    assert spectra.security_id == catalog_security_id("spectra-energy")
    assert sea.security_id == catalog_security_id("sea-limited")
    assert spectra.security_id != sea.security_id
    assert spectra.listing_id != sea.listing_id
    assert spectra.position_key != sea.position_key


@pytest.mark.unit
def test_esrx_propagates_express_scripts_not_ci() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    esrx = attach_signal_identities(
        [_signal("ESRX", date(2018, 6, 1))],
        resolver,
        date(2018, 6, 1),
        occupancy_by_ticker((membership("ESRX", date(2003, 9, 26), date(2018, 12, 21)),)),
    )[0]
    ci = attach_signal_identities(
        [_signal("CI", date(2018, 6, 1))],
        resolver,
        date(2018, 6, 1),
        occupancy_by_ticker((membership("CI", date(2000, 1, 3)),)),
    )[0]
    assert esrx.security_id == catalog_security_id("express-scripts")
    assert ci.security_id is None
    assert esrx.security_id != ci.security_id


@pytest.mark.unit
def test_unresolved_uses_pit_occupancy_listing_id() -> None:
    resolver = CatalogIdentityResolver(InMemorySecurityMaster())
    occupancy = membership("MSFT", date(1994, 6, 1))
    signals = attach_signal_identities(
        [_signal("MSFT")],
        resolver,
        date(2024, 6, 3),
        occupancy_by_ticker((occupancy,)),
    )
    target, orders, fills, positions = _propagate(signals)
    expected_listing = occupancy_listing_id(ticker="MSFT", exchange=None, valid_from=date(1994, 6, 1))
    for item in (signals[0], target.positions[0], orders[0], fills[0], positions[0]):
        assert item.security_id is None
        assert item.listing_id == expected_listing
        assert item.position_key == f"listing:{expected_listing}"
        assert "occupancy-unknown" not in (item.listing_id or "")


@pytest.mark.unit
def test_unresolved_recycled_occupancies_keep_distinct_listing_ids() -> None:
    resolver = CatalogIdentityResolver(InMemorySecurityMaster())
    first = attach_signal_identities(
        [_signal("SE", date(2015, 6, 1))],
        resolver,
        date(2015, 6, 1),
        occupancy_by_ticker((membership("SE", date(2007, 1, 3), date(2017, 2, 27)),)),
    )[0]
    second = attach_signal_identities(
        [_signal("SE", date(2018, 6, 1))],
        resolver,
        date(2018, 6, 1),
        occupancy_by_ticker((membership("SE", date(2017, 10, 20)),)),
    )[0]
    assert first.security_id is None and second.security_id is None
    assert first.listing_id != second.listing_id
    assert first.position_key != second.position_key


@pytest.mark.unit
def test_fill_keeps_order_identity_and_does_not_reresolve() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    signals = attach_signal_identities(
        [_signal("ESRX", date(2018, 12, 4))],
        resolver,
        date(2018, 12, 4),
        occupancy_by_ticker((membership("ESRX", date(2003, 9, 26), date(2018, 12, 21)),)),
    )
    _target, orders, fills, _positions = _propagate(signals, as_of=date(2018, 12, 4))
    later = resolver.resolve("ESRX", date(2019, 1, 2))
    assert later.security_id is None
    assert fills[0].security_id == catalog_security_id("express-scripts")
    assert fills[0].identity is orders[0].identity
    assert fills[0].identity is not later
