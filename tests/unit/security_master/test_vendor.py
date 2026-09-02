from datetime import date
from decimal import Decimal

import pytest

from app.backtest.data import load_market_data
from app.security_master.seed import load_known_identities_catalog
from app.security_master.vendor import vendor_fetch_symbols
from tests.fixtures.momentum import make_series


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


class _StubService:
    def __init__(self, bars_by_symbol: dict) -> None:
        self.bars_by_symbol = bars_by_symbol

    def get_history(self, symbol: str, start: date, end: date):
        bars = self.bars_by_symbol.get(symbol, [])
        return [
            bar
            for bar in bars
            if start <= bar.timestamp.date() <= end
        ]


@pytest.mark.unit
def test_antm_fetches_elv_vendor_symbol(master) -> None:
    names = vendor_fetch_symbols(master, "ANTM", date(2015, 1, 1), date(2022, 6, 1))
    assert names[0] == "ANTM"
    assert "ELV" in names


@pytest.mark.unit
def test_unresolved_listing_fetches_only_itself(master) -> None:
    assert vendor_fetch_symbols(master, "MSFT", date(2020, 1, 2), date(2020, 12, 31)) == ("MSFT",)


@pytest.mark.unit
def test_har_does_not_invent_a_yahoo_symbol(master) -> None:
    assert vendor_fetch_symbols(master, "HAR", date(2015, 1, 1), date(2017, 3, 1)) == ("HAR",)


@pytest.mark.unit
def test_ticker_change_does_not_split_fiserv(master) -> None:
    fisv = master.resolve_security("FISV", date(2020, 1, 2))
    fi = master.resolve_security("FI", date(2024, 1, 2))
    assert fisv.is_resolved and fi.is_resolved
    assert fisv.security is not None and fi.security is not None
    assert fisv.security.seed_key == fi.security.seed_key == "fiserv"


@pytest.mark.unit
def test_brk_b_vendor_symbol_differs_from_listing(master) -> None:
    names = vendor_fetch_symbols(master, "BRK.B", date(2015, 1, 1), date(2025, 12, 31))
    assert names == ("BRK.B", "BRK-B")


@pytest.mark.unit
def test_load_market_data_joins_vendor_bars_under_pit_ticker(master) -> None:
    elv = make_series("ELV", 5, start=date(2020, 1, 2), close=Decimal("80"))
    service = _StubService({"ANTM": [], "ELV": elv})
    loaded = load_market_data(
        service,  # type: ignore[arg-type]
        ["ANTM"],
        date(2020, 1, 10),
        date(2020, 1, 6),
        lookback_days=1,
        security_master=master,
    )
    assert [bar.symbol for bar in loaded["ANTM"]] == ["ELV"] * 5
    assert "ANTM" in loaded
