from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.universe.audit import (
    CLASS_OTHER,
    CLASS_VALID,
    PriceWindow,
    audit_universe,
    future_members_present,
)
from app.universe.models import ConstituentMembership
from tests.fixtures.universe import membership


def _interval(symbol: str, start: date, end: date | None = None) -> ConstituentMembership:
    return ConstituentMembership(
        symbol=symbol,
        start_date=start,
        end_date=end,
        source="fja05680/sp500",
        source_version="test",
    )


@pytest.mark.unit
def test_future_members_present_ignores_reentrants_with_valid_interval() -> None:
    periods = (
        membership("DOW", date(2010, 1, 1), date(2015, 1, 1)),
        membership("DOW", date(2019, 4, 1), None),
        membership("NEW", date(2024, 1, 1), None),
    )
    as_of = date(2012, 6, 1)
    selected = {"DOW", "NEW"}
    leaked = future_members_present(selected, periods, as_of)
    assert "DOW" not in leaked
    assert "NEW" in leaked


@pytest.mark.unit
def test_future_members_present_empty_for_correct_pit() -> None:
    periods = (
        membership("DOW", date(2010, 1, 1), date(2015, 1, 1)),
        membership("DOW", date(2019, 4, 1), None),
    )
    as_of = date(2012, 6, 1)
    selected = {"DOW"}
    assert future_members_present(selected, periods, as_of) == set()


@pytest.mark.unit
def test_audit_classifies_extreme_first_price_as_other() -> None:
    periods = (_interval("HAR", date(2006, 2, 1), date(2017, 3, 13)),)
    windows = {
        "HAR": PriceWindow(
            symbol="HAR",
            first_date=date(2013, 7, 8),
            last_date=date(2017, 3, 1),
            first_close=Decimal("18614.90"),
        )
    }
    report = audit_universe(
        periods,
        rebalance_dates=[date(2015, 1, 2)],
        price_windows=windows,
        investigate_symbols=["HAR"],
    )
    investigation = {item.symbol: item for item in report.investigations}["HAR"]
    assert investigation.classification == CLASS_OTHER
    assert "HAR" in report.extreme_first_price


@pytest.mark.unit
def test_audit_classifies_late_price_start_as_other() -> None:
    periods = (
        _interval("SE", date(2007, 1, 3), date(2017, 2, 27)),
        _interval("AAA", date(2000, 1, 1), None),
    )
    windows = {
        "SE": PriceWindow(
            symbol="SE",
            first_date=date(2017, 10, 20),
            last_date=date(2025, 12, 31),
            first_close=Decimal("16.25"),
        ),
        "AAA": PriceWindow(
            symbol="AAA",
            first_date=date(2000, 1, 3),
            last_date=date(2025, 12, 31),
            first_close=Decimal("50"),
        ),
    }
    report = audit_universe(
        periods,
        rebalance_dates=[date(2010, 1, 4)],
        price_windows=windows,
        investigate_symbols=["SE"],
    )
    investigation = {item.symbol: item for item in report.investigations}["SE"]
    assert investigation.classification == CLASS_OTHER
    assert "SE" in report.late_price_start


@pytest.mark.unit
def test_audit_classifies_valid_late_entrant() -> None:
    periods = (_interval("XYZ", date(2025, 7, 23), None),)
    windows = {
        "XYZ": PriceWindow(
            symbol="XYZ",
            first_date=date(2015, 11, 19),
            last_date=date(2025, 12, 31),
            first_close=Decimal("11"),
        )
    }
    report = audit_universe(
        periods,
        rebalance_dates=[date(2025, 8, 1)],
        price_windows=windows,
        investigate_symbols=["XYZ"],
    )
    investigation = {item.symbol: item for item in report.investigations}["XYZ"]
    assert investigation.classification == CLASS_VALID


@pytest.mark.unit
def test_universe_package_has_no_ticker_blacklist() -> None:
    root = Path("app/universe")
    forbidden = (
        "BLACKLIST",
        "EXCLUDE_TICKERS",
        "SUSPICIOUS_BLOCKLIST",
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} contains {token}"
        assert '{"XYZ", "TKO", "SE", "HAR"}' not in text
        assert "['XYZ', 'TKO', 'SE', 'HAR']" not in text
