from datetime import date
from decimal import Decimal

import pytest

from app.data.identity_quality import (
    REASON_IDENTITY_MISMATCH,
    apply_identity,
    assess_identity_series,
)
from app.security_master.seed import load_known_identities_catalog
from tests.fixtures.momentum import make_series


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


@pytest.mark.unit
def test_unmapped_symbol_is_not_guessed(master) -> None:
    bars = make_series("MSFT", 10, start=date(2020, 1, 2), close=Decimal("50"))
    clipped, unusable = apply_identity({"MSFT": bars}, master)
    assert unusable == {}
    assert clipped["MSFT"] == tuple(bars)


@pytest.mark.unit
def test_har_series_is_identity_mismatch_without_blacklist(master) -> None:
    bars = make_series("HAR", 20, start=date(2015, 1, 2), close=Decimal("50"))
    assessment = assess_identity_series("HAR", bars, master)
    assert assessment.usable is False
    assert assessment.reason == REASON_IDENTITY_MISMATCH
    assert assessment.bars == tuple(bars)


@pytest.mark.unit
def test_tko_predecessor_bars_are_clipped(master) -> None:
    bars = make_series("TKO", 20, start=date(2023, 9, 1), close=Decimal("80"))
    assessment = assess_identity_series("TKO", bars, master)
    assert assessment.usable is True
    assert assessment.reason is None
    kept_dates = [bar.timestamp.date() for bar in assessment.bars]
    assert date(2023, 9, 11) not in kept_dates
    assert date(2023, 9, 12) in kept_dates
    assert all(session >= date(2023, 9, 12) for session in kept_dates)


@pytest.mark.unit
def test_xyz_yahoo_continuity_keeps_predecessor_labeled_bars(master) -> None:
    bars = make_series("XYZ", 10, start=date(2016, 1, 4), close=Decimal("13"))
    assessment = assess_identity_series("XYZ", bars, master)
    assert assessment.usable is True
    assert len(assessment.bars) == 10


@pytest.mark.unit
def test_gme_identity_matches(master) -> None:
    bars = make_series("GME", 10, start=date(2020, 1, 2), close=Decimal("10"))
    clipped, unusable = apply_identity({"GME": bars}, master)
    assert unusable == {}
    assert clipped["GME"] == tuple(bars)


@pytest.mark.unit
def test_empty_master_does_not_change_series() -> None:
    bars = make_series("HAR", 5, start=date(2015, 1, 2), close=Decimal("50"))
    clipped, unusable = apply_identity({"HAR": bars}, None)
    assert unusable == {}
    assert clipped["HAR"] == tuple(bars)


@pytest.mark.unit
def test_se_vendor_bars_are_sea_limited_only(master) -> None:
    bars = make_series("SE", 5, start=date(2018, 1, 2), close=Decimal("16"))
    assessment = assess_identity_series("SE", bars, master)
    assert assessment.usable is True
    assert len(assessment.bars) == 5


@pytest.mark.unit
def test_vendor_bars_under_pit_ticker_resolve_same_security(master) -> None:
    bars = make_series("ELV", 10, start=date(2020, 1, 2), close=Decimal("80"))
    assessment = assess_identity_series("ANTM", bars, master)
    assert assessment.usable is True
    assert assessment.reason is None
    assert [bar.symbol for bar in assessment.bars] == ["ELV"] * 10


@pytest.mark.unit
def test_para_local_series_is_identity_mismatch(master) -> None:
    bars = make_series("PARA", 10, start=date(2023, 1, 3), close=Decimal("101500"))
    assessment = assess_identity_series("PARA", bars, master)
    assert assessment.usable is False
    assert assessment.reason == REASON_IDENTITY_MISMATCH


@pytest.mark.unit
def test_unresolved_does_not_become_valid_identity(master) -> None:
    bars = make_series("AVB", 10, start=date(2020, 1, 2), close=Decimal("150"))
    clipped, unusable = apply_identity({"AVB": bars}, master)
    assert unusable == {}
    assert master.resolve_security("AVB", date(2020, 1, 2)).is_resolved is False
    assert clipped["AVB"] == tuple(bars)
