from datetime import date

import pytest

from app.security_master.seed import load_known_identities_catalog


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


@pytest.mark.unit
def test_se_recycling_two_securities(master) -> None:
    spectra = master.resolve_security("SE", date(2015, 6, 1))
    sea = master.resolve_security("SE", date(2018, 6, 1))
    assert spectra.is_resolved and sea.is_resolved
    assert spectra.security is not None and sea.security is not None
    assert spectra.security.seed_key == "spectra-energy"
    assert sea.security.seed_key == "sea-limited"
    assert spectra.security.seed_key != sea.security.seed_key
    vendor_2015 = master.resolve_market_data_symbol("SE", date(2015, 6, 1))
    vendor_2018 = master.resolve_market_data_symbol("SE", date(2018, 6, 1))
    assert vendor_2015.is_resolved is False
    assert vendor_2018.security is not None
    assert vendor_2018.security.seed_key == "sea-limited"


@pytest.mark.unit
def test_xyz_ticker_change_same_security_with_yahoo_continuity(master) -> None:
    listing_2016 = master.resolve_security("XYZ", date(2016, 1, 4))
    listing_2025 = master.resolve_security("XYZ", date(2025, 6, 1))
    sq = master.resolve_security("SQ", date(2016, 1, 4))
    vendor_2016 = master.resolve_market_data_symbol("XYZ", date(2016, 1, 4))
    assert listing_2016.is_resolved is False
    assert listing_2025.is_resolved and sq.is_resolved and vendor_2016.is_resolved
    assert listing_2025.security is not None and sq.security is not None
    assert vendor_2016.security is not None
    assert listing_2025.security.seed_key == sq.security.seed_key == vendor_2016.security.seed_key
    history = master.get_ticker_history("block-inc-class-a")
    xyz_listing = next(item for item in history if item.ticker == "XYZ")
    yahoo = next(
        item
        for item in master.tickers()
        if item.scheme == "yahoo" and item.ticker == "XYZ"
    )
    assert xyz_listing.continuity is False
    assert yahoo.continuity is True
    assert yahoo.valid_from == date(2015, 11, 19)


@pytest.mark.unit
def test_tko_is_new_issuer_without_predecessor_continuity(master) -> None:
    before = master.resolve_security("TKO", date(2020, 1, 2))
    after = master.resolve_security("TKO", date(2024, 1, 2))
    vendor_before = master.resolve_market_data_symbol("TKO", date(2013, 7, 8))
    vendor_after = master.resolve_market_data_symbol("TKO", date(2023, 9, 12))
    assert before.is_resolved is False
    assert vendor_before.is_resolved is False
    assert after.is_resolved and vendor_after.is_resolved
    assert after.security is not None
    assert after.security.seed_key == "tko-group-holdings"
    yahoo = next(
        item
        for item in master.tickers()
        if item.scheme == "yahoo" and item.ticker == "TKO"
    )
    assert yahoo.continuity is False
    assert yahoo.valid_from == date(2023, 9, 12)


@pytest.mark.unit
def test_har_listing_is_harman_and_yahoo_is_unresolved(master) -> None:
    listing = master.resolve_security("HAR", date(2015, 6, 1))
    after_delist = master.resolve_security("HAR", date(2018, 1, 2))
    vendor = master.resolve_market_data_symbol("HAR", date(2015, 6, 1))
    assert listing.is_resolved
    assert listing.security is not None
    assert listing.security.seed_key == "harman-international"
    assert after_delist.is_resolved is False
    assert vendor.is_resolved is False
    assert master.has_vendor_mapping("HAR") is False


@pytest.mark.unit
def test_gme_membership_and_market_data_same_security(master) -> None:
    listing = master.resolve_security("GME", date(2020, 1, 2))
    vendor = master.resolve_market_data_symbol("GME", date(2020, 1, 2))
    assert listing.is_resolved and vendor.is_resolved
    assert listing.security is not None and vendor.security is not None
    assert listing.security.seed_key == vendor.security.seed_key == "gamestop"


@pytest.mark.unit
def test_antm_and_elv_are_the_same_security(master) -> None:
    listing = master.resolve_security("ANTM", date(2020, 1, 2))
    later = master.resolve_security("ELV", date(2023, 1, 3))
    vendor = master.resolve_market_data_symbol("ELV", date(2016, 1, 4))
    assert listing.is_resolved and later.is_resolved and vendor.is_resolved
    assert listing.security is not None and later.security is not None
    assert vendor.security is not None
    assert listing.security.seed_key == later.security.seed_key == vendor.security.seed_key


@pytest.mark.unit
def test_para_listing_has_no_yahoo_mapping(master) -> None:
    listing = master.resolve_security("PARA", date(2023, 6, 1))
    vendor = master.resolve_market_data_symbol("PARA", date(2023, 6, 1))
    assert listing.is_resolved
    assert listing.security is not None
    assert listing.security.seed_key == "paramount-global"
    assert vendor.is_resolved is False
    assert master.has_vendor_mapping("PARA") is False
