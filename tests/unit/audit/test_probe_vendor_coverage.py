from pathlib import Path

import pytest

from scripts.probe_vendor_coverage import (
    FROZEN_SAMPLE,
    FrozenSample,
    ProbeRow,
    apply_live_sample_lookups,
    apply_recycle_identity_rules,
    assert_trial_output_dir,
    classify_live_row,
    compare_ticker_change_pairs,
    coverage_status_for_dates,
    empty_lookup_result,
    store_current_lookup,
    store_delisted_lookup,
    _docs_row,
)


EXPECTED_SUFFIXES = {
    ("ATVI", "2015-08-31→2023-10-18"): "ATVI-202310",
    ("CELG", "2006-11-06→2019-11-21"): "CELG-201911",
    ("XLNX", "1999-11-08→2022-02-15"): "XLNX-202202",
    ("FRC", "2019-01-02→2023-05-04"): "FRC-202305",
    ("SIVB", "2018-03-19→2023-03-15"): "SIVB-202303",
    ("CBS", "1996-01-02→2019-12-05"): "CBS-201912",
    ("VIAB", "2006-01-03→2019-12-05"): "VIAB-201912",
    ("VIAC", "2019-12-05→2022-02-17"): "VIAC-202202",
    ("LLL", "2004-12-01→2019-07-01"): "LLL-201907",
    ("RTN", "1996-01-02→2020-04-06"): "RTN-202004",
    ("DWDP", "2017-09-01→2019-06-03"): "DWDP-201906",
    ("COG", "2008-06-23→2021-10-04"): "COG-202110",
    ("SYMC", "2003-03-31→2019-11-05"): "SYMC-201911",
    ("PKI", "1996-01-02→2023-05-16"): "PKI-202305",
    ("DO", "2009-02-26→2016-10-03"): "DO-201610",
    ("CHK", "2006-03-03→2018-03-19"): "CHK-201803",
    ("CA", "1996-01-02→2018-11-06"): "CA-201811",
    ("ADS", "2013-12-23→2020-06-22"): "ADS-202006",
    ("SE", "2015 (Spectra Energy occupancy)"): "SE-201702",
    ("HAR", "2006-02-01→2017-03-13 (Harman International)"): "HAR-201703",
    ("ESRX", "2003-09-26→2018-12-21"): "ESRX-201812",
    ("SQ", "2015-11-19→2025-01-21 (Block Class A predecessor ticker)"): "SQ-202501",
    ("WWE", "predecessor of TKO (must not be silent TKO history)"): "WWE-202309",
}

NO_SUFFIX_TICKER_PERIODS = {
    ("AVB", "2007-01-10→open"),
    ("EA", "2002-07-22→open"),
    ("EQR", "2001-12-03→open"),
    ("BK", "1996-01-02→2026-05-21"),
    ("MMC", "1996-01-02→2026-01-14"),
    ("HOLX", "2016-03-30→2026-04-09"),
    ("CTRA", "2021-10-04→2026-05-07"),
    ("GEN", "2022-11-08→open"),
    ("RVTY", "2023-05-16→open"),
    ("SE", "2018 (Sea Limited occupancy)"),
    ("HAR", "current namesake lookup"),
    ("XYZ", "2025-01-21→open (Block Class A successor ticker)"),
    ("TKO", "2023-09-12→open (TKO Group Holdings)"),
    ("GME", "2013-07-08→2025-12-31 control"),
}


class FakeNorgate:
    class StockPriceAdjustmentType:
        TOTALRETURN = "TOTALRETURN"
        NONE = "NONE"

    def __init__(self, catalog: dict[str, dict[str, object]]) -> None:
        self.catalog = catalog
        self.symbols_requested: list[str] = []

    def assetid(self, symbol: str) -> object:
        self.symbols_requested.append(symbol)
        if symbol not in self.catalog:
            raise RuntimeError(f"assetid: {symbol} not found")
        return self.catalog[symbol]["assetid"]

    def security_name(self, symbol: str) -> str:
        return str(self.catalog[symbol]["name"])

    def exchange_name(self, symbol: str) -> str:
        return "NYSE"

    def symbol(self, assetid: object) -> str:
        for symbol, row in self.catalog.items():
            if str(row["assetid"]) == str(assetid):
                return str(row.get("vendor_symbol", symbol))
        return str(assetid)

    def first_quoted_date(self, symbol: str) -> str:
        return str(self.catalog[symbol]["first"])

    def last_quoted_date(self, symbol: str) -> str:
        return str(self.catalog[symbol]["last"])

    def price_timeseries(self, symbol: str, **kwargs: object) -> list[int]:
        bars = self.catalog[symbol].get("bars", [1, 2, 3])
        return list(bars) if isinstance(bars, list) else []


def _sample(ticker: str, period_contains: str | None = None) -> FrozenSample:
    matches = [sample for sample in FROZEN_SAMPLE if sample.ticker == ticker]
    if period_contains:
        matches = [sample for sample in matches if period_contains in sample.historical_period]
    assert len(matches) == 1, ticker
    return matches[0]


def _hit(
    symbol: str,
    assetid: str,
    name: str,
    first: str,
    last: str,
    vendor_symbol: str | None = None,
) -> dict[str, object]:
    result = empty_lookup_result(symbol)
    result.update(
        {
            "found": True,
            "assetid": assetid,
            "security_name": name,
            "vendor_symbol": vendor_symbol or symbol,
            "first_date": first,
            "last_date": last,
            "daily_ohlcv": "YES",
            "adjusted_close": "YES",
            "corporate_action_handling": "NOT_TESTABLE",
        }
    )
    return result


@pytest.mark.unit
def test_frozen_sample_has_37_rows_and_protocol_suffixes() -> None:
    assert len(FROZEN_SAMPLE) == 37
    observed = {(sample.ticker, sample.historical_period): sample.delisted_suffix for sample in FROZEN_SAMPLE}
    for key, suffix in EXPECTED_SUFFIXES.items():
        assert observed[key] == suffix
    for key in NO_SUFFIX_TICKER_PERIODS:
        assert observed[key] is None
    assert sum(1 for sample in FROZEN_SAMPLE if sample.delisted_suffix) == 23


@pytest.mark.unit
def test_gme_and_still_listed_rows_do_not_use_pit_exit_as_delist_month() -> None:
    assert _sample("GME").delisted_suffix is None
    assert _sample("BK").delisted_suffix is None
    assert _sample("AVB").delisted_suffix is None


@pytest.mark.unit
def test_trial_quoted_dates_are_not_coverage_fail() -> None:
    sample = _sample("GME")
    assert coverage_status_for_dates("2024-09-03", "2026-09-02", sample) == "NOT_TESTABLE"


@pytest.mark.unit
def test_atvi_suffix_miss_stays_not_testable() -> None:
    sample = _sample("ATVI")
    row = _docs_row(sample)
    current = empty_lookup_result("ATVI", "assetid: ATVI not found")
    suffix = empty_lookup_result("ATVI-202310", "assetid: ATVI-202310 not found")
    store_current_lookup(row, current)
    store_delisted_lookup(row, suffix)
    classify_live_row(row, sample, current, suffix)
    assert row.identity_status == "NOT_TESTABLE"
    assert row.coverage_status == "NOT_TESTABLE"
    assert row.vendor_security_id == ""
    assert "PASS" not in {row.identity_status, row.coverage_status}


@pytest.mark.unit
def test_current_namesake_is_not_historical_identity() -> None:
    sample = _sample("SE", "2015")
    row = _docs_row(sample)
    current = _hit("SE", "111", "Sea Limited", "2017-10-20", "2026-09-02")
    suffix = empty_lookup_result("SE-201702", "not found")
    store_current_lookup(row, current)
    store_delisted_lookup(row, suffix)
    classify_live_row(row, sample, current, suffix)
    assert row.identity_status == "NOT_TESTABLE"
    assert row.vendor_security_id == ""
    assert row.current_asset_id == "111"
    assert "not historical identity" in row.notes


@pytest.mark.unit
def test_suffix_hit_with_trial_window_is_live_partial_not_pass() -> None:
    sample = _sample("ATVI")
    row = _docs_row(sample)
    current = empty_lookup_result("ATVI", "not found")
    suffix = _hit(
        "ATVI-202310",
        "2750000",
        "Activision Blizzard",
        "2024-09-03",
        "2026-09-02",
        vendor_symbol="ATVI-202310",
    )
    classify_live_row(row, sample, current, suffix)
    assert row.identity_status == "LIVE_PARTIAL"
    assert row.coverage_status == "NOT_TESTABLE"
    assert row.vendor_security_id == "2750000"
    assert row.identity_source == "delisted_suffix"
    assert row.identity_status != "PASS"


@pytest.mark.unit
def test_alias_to_acquirer_is_fail() -> None:
    sample = _sample("ATVI")
    row = _docs_row(sample)
    current = empty_lookup_result("ATVI", "not found")
    suffix = _hit("ATVI-202310", "1", "Microsoft", "2015-08-31", "2023-10-18", vendor_symbol="MSFT")
    classify_live_row(row, sample, current, suffix)
    assert row.identity_status == "FAIL"


@pytest.mark.unit
def test_ticker_change_same_assetid_is_recorded() -> None:
    rows = [_docs_row(sample) for sample in FROZEN_SAMPLE]
    cog = next(row for row in rows if row.ticker == "COG")
    ctra = next(row for row in rows if row.ticker == "CTRA")
    cog.delisted_asset_id = "9001"
    ctra.current_asset_id = "9001"
    matches = compare_ticker_change_pairs(rows)
    assert matches["COG->CTRA"] == "YES"
    assert cog.ticker_change_assetid_match == "YES"


@pytest.mark.unit
def test_ticker_change_missing_predecessor_is_not_testable() -> None:
    rows = [_docs_row(sample) for sample in FROZEN_SAMPLE]
    ctra = next(row for row in rows if row.ticker == "CTRA")
    ctra.current_asset_id = "9001"
    matches = compare_ticker_change_pairs(rows)
    assert matches["COG->CTRA"] == "NOT_TESTABLE"


@pytest.mark.unit
def test_recycle_collapse_is_fail_only_when_both_occupancies_resolve() -> None:
    rows = [_docs_row(sample) for sample in FROZEN_SAMPLE]
    se_2015 = next(row for row in rows if row.ticker == "SE" and "2015" in row.historical_period)
    se_2018 = next(row for row in rows if row.ticker == "SE" and "2018" in row.historical_period)
    se_2015.delisted_asset_id = "5"
    se_2018.current_asset_id = "5"
    se_2015.identity_status = "LIVE_PARTIAL"
    apply_recycle_identity_rules(rows)
    assert se_2015.identity_status == "FAIL"


@pytest.mark.unit
def test_apply_live_lookups_requests_frozen_suffixes_not_a_scan() -> None:
    rows = [_docs_row(sample) for sample in FROZEN_SAMPLE]
    client = FakeNorgate(
        {
            "GME": {
                "assetid": 42,
                "name": "GameStop Corp.",
                "first": "2024-09-03",
                "last": "2026-09-02",
                "bars": [1, 2, 3],
            }
        }
    )
    meta = apply_live_sample_lookups(client, rows, delisted_db_present=True)
    assert meta["database_symbols_called"] is False
    assert "ATVI-202310" in client.symbols_requested
    assert "SE-201702" in client.symbols_requested
    assert "GME-201604" not in client.symbols_requested
    gme = next(row for row in rows if row.ticker == "GME")
    assert gme.identity_status == "LIVE_PARTIAL"
    assert gme.coverage_status == "NOT_TESTABLE"
    atvi = next(row for row in rows if row.ticker == "ATVI")
    assert atvi.identity_status == "NOT_TESTABLE"


@pytest.mark.unit
def test_refuses_to_overwrite_audit_vendor_coverage_probe(tmp_path: Path) -> None:
    assert_trial_output_dir(tmp_path / "norgate_trial")
    with pytest.raises(SystemExit, match="audit/norgate_trial"):
        assert_trial_output_dir(Path("audit"))


@pytest.mark.unit
def test_probe_source_does_not_call_database_symbols() -> None:
    source = Path("scripts/probe_vendor_coverage.py").read_text(encoding="utf-8")
    assert "database_symbols(" not in source
    assert "MarketDataService" not in source
    assert "market_bars" in source  # mentioned only as something the probe must not write
