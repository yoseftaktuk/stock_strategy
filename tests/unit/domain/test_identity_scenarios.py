from datetime import date

import pytest

from app.domain.models.identity import IdentityRef, PositionKey
from app.domain.models.listing import Listing
from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.identity_resolver import CatalogIdentityResolver, catalog_security_id
from app.security_master.seed import load_known_identities_catalog


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


@pytest.fixture(scope="module")
def resolver(master) -> CatalogIdentityResolver:
    return CatalogIdentityResolver.from_catalog(master)


@pytest.mark.unit
def test_sq_rename_to_xyz_same_security_and_position_key(resolver) -> None:
    sq = resolver.resolve("SQ", date(2024, 6, 3))
    xyz = resolver.resolve("XYZ", date(2025, 6, 2))
    expected = catalog_security_id("block-inc-class-a")
    assert sq.is_resolved and xyz.is_resolved
    assert sq.security_id == xyz.security_id == expected
    assert sq.security_id not in {"SQ", "XYZ"}
    assert sq.ticker_as_of == "SQ"
    assert xyz.ticker_as_of == "XYZ"
    assert sq.listing.listing_id != xyz.listing.listing_id
    assert sq.listing.ticker != xyz.listing.ticker
    assert sq.position_key() == xyz.position_key() == PositionKey.for_security(expected)


@pytest.mark.unit
def test_se_recycle_different_security_and_position_key(resolver) -> None:
    spectra = resolver.resolve("SE", date(2015, 6, 1))
    sea = resolver.resolve("SE", date(2018, 6, 1))
    assert spectra.is_resolved and sea.is_resolved
    assert spectra.security_id == catalog_security_id("spectra-energy")
    assert sea.security_id == catalog_security_id("sea-limited")
    assert spectra.security_id != sea.security_id
    assert spectra.security_id not in {"SE", "spectra", "sea"}
    assert spectra.ticker_as_of == sea.ticker_as_of == "SE"
    assert spectra.listing.listing_id != sea.listing.listing_id
    assert spectra.position_key() != sea.position_key()
    assert resolver.resolve("SE", date(2017, 6, 1)).is_resolved is False


@pytest.mark.unit
def test_esrx_is_terminal_predecessor_and_does_not_resolve_to_ci(resolver, master) -> None:
    esrx = resolver.resolve("ESRX", date(2018, 6, 1))
    ci = resolver.resolve("CI", date(2018, 6, 1))
    after = resolver.resolve("ESRX", date(2019, 1, 2))
    express = master.get_security("express-scripts")
    assert express is not None
    assert express.status == "DELISTED"
    assert esrx.is_resolved
    assert esrx.security_id == catalog_security_id("express-scripts")
    assert esrx.security_id != catalog_security_id("cigna")
    assert esrx.ticker_as_of == "ESRX"
    assert ci.security_id is None
    assert ci.is_resolved is False
    assert after.is_resolved is False
    assert after.security_id is None
    assert resolver.security_id_for_seed_key("express-scripts") == esrx.security_id


@pytest.mark.unit
def test_unresolved_unknown_ticker_does_not_mint_security(resolver, master) -> None:
    msft = resolver.resolve("MSFT", date(2023, 6, 1))
    assert msft.is_resolved is False
    assert msft.security_id is None
    assert msft.ticker_as_of == "MSFT"
    assert master.get_security("msft") is None
    assert master.get_security("MSFT") is None
    assert resolver.security_id_for_seed_key("msft") is None
    assert msft.position_key().kind == "listing"


@pytest.mark.unit
def test_unresolved_recycled_ticker_occupancies_have_different_position_keys() -> None:
    first = Listing(ticker="SE", valid_from=date(2007, 1, 3), valid_to=date(2017, 2, 27))
    second = Listing(ticker="SE", valid_from=date(2017, 10, 20))
    resolver = CatalogIdentityResolver(listings=(first, second))
    spectra = resolver.resolve("SE", date(2015, 6, 1))
    sea = resolver.resolve("SE", date(2018, 6, 1))
    assert spectra.security_id is None and sea.security_id is None
    assert spectra.is_resolved is False and sea.is_resolved is False
    assert spectra.ticker_as_of == sea.ticker_as_of == "SE"
    assert first.listing_id != second.listing_id
    assert spectra.position_key() != sea.position_key()
    assert spectra.position_key() == PositionKey.for_listing(first.listing_id)
    assert sea.position_key() == PositionKey.for_listing(second.listing_id)
    domain_first = IdentityRef.unresolved(listing=first, ticker_as_of="SE")
    domain_second = IdentityRef.unresolved(listing=second, ticker_as_of="SE")
    assert domain_first.position_key() != domain_second.position_key()


@pytest.mark.unit
def test_empty_catalog_does_not_mint_or_guess_identities() -> None:
    master = InMemorySecurityMaster()
    resolver = CatalogIdentityResolver(master)
    aapl = resolver.resolve("AAPL", date(2023, 6, 1))
    msft = resolver.resolve("MSFT", date(2024, 1, 2))
    assert master.securities() == ()
    assert aapl.security_id is None and msft.security_id is None
    assert aapl.position_key() != PositionKey.for_security("AAPL")
    assert aapl.security_id != "AAPL"
    later = resolver.resolve("MSFT", date(2024, 6, 3))
    assert msft.position_key() == later.position_key()
