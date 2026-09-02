from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.pit_coverage import (
    MARKET_MISSING,
    QUALITY_NA,
    REASON_C_TICKER_RECYCLED,
    REASON_D_UNRESOLVED_IDENTITY,
    REASON_F_DELISTED,
    REASON_G_DATA_UNDER_OTHER_TICKER,
    REASON_H_IDENTITY_VALIDATION_FAILED,
    build_pit_coverage,
)
from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.seed import load_known_identities_catalog
from app.universe.audit import PriceWindow
from tests.fixtures.universe import membership


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


@pytest.mark.unit
def test_pit_member_without_prices_is_missing_and_kept(master) -> None:
    periods = (membership("MISS", date(2010, 1, 1), date(2020, 1, 1)),)
    report = build_pit_coverage(
        periods,
        {},
        master,
        start=date(2015, 1, 1),
        end=date(2015, 12, 31),
    )
    row = report.rows[0]
    assert row.historical_ticker == "MISS"
    assert row.local_listing_csv is False
    assert row.market_data_status == MARKET_MISSING
    assert row.coverage_days == 0
    assert row.reason == REASON_D_UNRESOLVED_IDENTITY
    assert periods[0].symbol == "MISS"
    assert report.missing == 1


@pytest.mark.unit
def test_ticker_change_uses_vendor_csv_for_pit_coverage(master) -> None:
    periods = (membership("ANTM", date(2002, 7, 25), date(2022, 6, 28)),)
    windows = {
        "ELV": PriceWindow(
            symbol="ELV",
            first_date=date(2013, 7, 8),
            last_date=date(2025, 12, 31),
            first_close=Decimal("83"),
        )
    }
    report = build_pit_coverage(
        periods,
        windows,
        master,
        start=date(2015, 1, 1),
        end=date(2022, 6, 27),
    )
    row = report.rows[0]
    assert row.identity_status == "RESOLVED"
    assert row.seed_key == "elevance-health"
    assert row.vendor_symbol == "ELV"
    assert row.reason == REASON_G_DATA_UNDER_OTHER_TICKER
    assert row.coverage_ratio > 0
    assert row.local_listing_csv is False


@pytest.mark.unit
def test_partial_coverage_when_prices_start_after_membership(master) -> None:
    periods = (membership("SE", date(2007, 1, 3), date(2017, 2, 27)),)
    windows = {
        "SE": PriceWindow(
            symbol="SE",
            first_date=date(2017, 10, 20),
            last_date=date(2025, 12, 31),
            first_close=Decimal("16.26"),
        )
    }
    report = build_pit_coverage(
        periods,
        windows,
        master,
        start=date(2015, 1, 1),
        end=date(2017, 2, 26),
    )
    row = report.rows[0]
    assert row.coverage_days == 0
    assert row.coverage_ratio == 0
    assert row.reason == REASON_C_TICKER_RECYCLED
    assert row.market_data_status == MARKET_MISSING


@pytest.mark.unit
def test_delisted_aligned_end_is_not_a_ticker_change(master) -> None:
    periods = (membership("ESRX", date(2003, 9, 26), date(2018, 12, 21)),)
    windows = {
        "ESRX": PriceWindow(
            symbol="ESRX",
            first_date=date(2013, 7, 8),
            last_date=date(2018, 12, 21),
            first_close=Decimal("63.27"),
        )
    }
    report = build_pit_coverage(
        periods,
        windows,
        master,
        start=date(2015, 1, 1),
        end=date(2018, 12, 21),
    )
    row = report.rows[0]
    assert row.reason == REASON_F_DELISTED
    assert row.reason != "B_ticker_change"
    assert row.identity_status == "RESOLVED"
    assert row.coverage_ratio == 1.0
    assert row.local_listing_csv is True


@pytest.mark.unit
def test_har_overlapping_wrong_vendor_is_identity_failed(master) -> None:
    periods = (membership("HAR", date(2006, 2, 1), date(2017, 3, 13)),)
    windows = {
        "HAR": PriceWindow(
            symbol="HAR",
            first_date=date(2013, 7, 8),
            last_date=date(2022, 3, 2),
            first_close=Decimal("18614.90"),
        )
    }
    report = build_pit_coverage(
        periods,
        windows,
        master,
        start=date(2015, 1, 1),
        end=date(2017, 3, 12),
    )
    row = report.rows[0]
    assert row.reason == REASON_H_IDENTITY_VALIDATION_FAILED
    assert row.quality_status == "unusable"
    assert row.identity_status == "RESOLVED"
    assert row.coverage_days == 0


@pytest.mark.unit
def test_unresolved_identity_is_not_invented() -> None:
    master = InMemorySecurityMaster()
    periods = (membership("ZZZ", date(2010, 1, 1), None),)
    report = build_pit_coverage(
        periods,
        {},
        master,
        start=date(2015, 1, 1),
        end=date(2015, 12, 31),
    )
    assert report.rows[0].identity_status == "UNRESOLVED"
    assert report.rows[0].seed_key is None
    assert report.rows[0].quality_status == QUALITY_NA


@pytest.mark.unit
def test_pit_coverage_package_has_no_ticker_blacklist() -> None:
    path = Path("app/data/pit_coverage.py")
    text = path.read_text(encoding="utf-8")
    for token in ("BLACKLIST", "EXCLUDE_TICKERS", "SUSPICIOUS_BLOCKLIST"):
        assert token not in text
    assert '{"HAR", "PARA", "TEG", "CCE"}' not in text
    vendor = Path("app/security_master/vendor.py").read_text(encoding="utf-8")
    for token in ("BLACKLIST", "EXCLUDE_TICKERS", "SUSPICIOUS_BLOCKLIST"):
        assert token not in vendor
