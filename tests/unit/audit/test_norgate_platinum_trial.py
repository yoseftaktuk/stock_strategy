"""Unit tests for the isolated Norgate Platinum trial helpers.

Does not require NDU. Does not modify the existing vendor-coverage probe tests
except by importing FROZEN_SAMPLE.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.norgate_trial.bars import (
    StagedBar,
    bars_from_timeseries,
    interior_gaps,
    series_cover_occupancy,
    validate_staged_bars,
    write_bar_csv,
)
from app.norgate_trial.client import (
    LookupResult,
    discover_delisted_suffixes,
    evaluate_package_proof,
    lookup_symbol,
)
from app.norgate_trial.constants import (
    JOIN_AS_OF_DATES,
    SEA_TRIAL_ASSET_ID,
    STATUS_FAIL,
    STATUS_NOT_TESTABLE,
    STATUS_PASS,
    TRIAL_HISTORY_START,
    VERDICT_NOT_SUITABLE,
    VERDICT_SUITABLE,
)
from app.norgate_trial.frozen import (
    apply_recycle_identity_rules,
    classify_frozen_row,
    compare_ticker_change_pairs,
    coverage_status_for_dates,
    frozen_suffix_map,
)
from app.norgate_trial.occupancy import (
    Occupancy,
    OccupancyMapping,
    build_occupancies,
    current_ticker_contamination,
    may_use_current_ticker,
    occupancy_for_as_of,
    provisional_seed_key,
)
from app.norgate_trial.paths import IsolationError, assert_not_production_write, assert_trial_output_dir
from app.norgate_trial.sample import frozen_sample
from app.norgate_trial.validation import (
    GateResult,
    build_verdict,
    gate_f1,
    gate_j1,
    gate_p0,
    gate_u1,
)
from app.security_master.seed import load_known_identities_catalog
from app.universe.models import ConstituentMembership
from scripts.probe_vendor_coverage import FROZEN_SAMPLE


class FakeNorgate:
    class StockPriceAdjustmentType:
        TOTALRETURN = "TOTALRETURN"
        NONE = "NONE"

    class PaddingType:
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

    def price_timeseries(self, symbol: str, **kwargs: object) -> list[dict[str, object]]:
        bars = self.catalog[symbol].get("bars")
        if isinstance(bars, list):
            return list(bars)
        return [{"Date": "2013-07-08", "Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 10}]

    def database_symbols(self, database: str | None = None) -> list[str]:
        return [symbol for symbol in self.catalog if "-" in symbol]


def _hit(symbol: str, assetid: str, name: str, first: str, last: str = "") -> LookupResult:
    result = LookupResult(symbol=symbol, found=True)
    result.assetid = assetid
    result.vendor_symbol = symbol
    result.security_name = name
    result.first_date = first
    result.last_date = last
    result.daily_ohlcv = "YES"
    result.adjusted_close = "YES"
    return result


def _miss(symbol: str) -> LookupResult:
    return LookupResult(symbol=symbol, error="NOT_FOUND")


def _sample(ticker: str, period_contains: str | None = None):
    matches = [sample for sample in FROZEN_SAMPLE if sample.ticker == ticker]
    if period_contains:
        matches = [sample for sample in matches if period_contains in sample.historical_period]
    assert len(matches) == 1, ticker
    return matches[0]


def _bar(day: str, close: str = "10", adjusted: str | None = "10") -> StagedBar:
    parsed = date.fromisoformat(day)
    return StagedBar(
        symbol="GME",
        timestamp=datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adjusted_close=None if adjusted is None else Decimal(adjusted),
        volume=1000,
    )


@pytest.mark.unit
def test_frozen_sample_loader_matches_probe() -> None:
    loaded = frozen_sample()
    assert len(loaded) == 37
    assert loaded[0].ticker == FROZEN_SAMPLE[0].ticker
    assert loaded[0].delisted_suffix == FROZEN_SAMPLE[0].delisted_suffix
    assert len(FROZEN_SAMPLE) == 37
    suffixes = frozen_suffix_map(list(FROZEN_SAMPLE))
    assert suffixes["ATVI"] == "ATVI-202310"
    assert suffixes["SE"] == "SE-201702"
    assert "GME" not in suffixes


@pytest.mark.unit
def test_isolation_rejects_trial_and_production_paths() -> None:
    with pytest.raises(IsolationError):
        assert_trial_output_dir(Path("audit/norgate_trial"))
    with pytest.raises(IsolationError):
        assert_not_production_write(Path("data/raw/GME.csv"))
    with pytest.raises(IsolationError):
        assert_not_production_write(Path("data/security_master/known_identities.json"))
    with pytest.raises(IsolationError):
        assert_not_production_write(Path("app/data/factory.py"))
    with pytest.raises(IsolationError):
        assert_not_production_write(Path("audit/vendor_coverage_probe.json"))
    resolved = assert_trial_output_dir(Path("audit/norgate_platinum_trial/frozen_sample.json"))
    assert "norgate_platinum_trial" in resolved.parts


@pytest.mark.unit
def test_package_proof_passes_trial_depth() -> None:
    lookups = {
        "GME": _hit("GME", "124739", "GameStop", TRIAL_HISTORY_START.isoformat()),
        "AVB": _hit("AVB", "1", "AvalonBay", TRIAL_HISTORY_START.isoformat()),
    }
    proof = evaluate_package_proof(
        ndu_running=True,
        databases=["US Equities", "US Equities Delisted"],
        proof_lookups=lookups,
        delisted_match_count=0,
        errors=[],
    )
    assert proof.verdict == STATUS_PASS
    assert proof.trial_capped is True
    assert proof.delisted_populated is False


@pytest.mark.unit
def test_package_proof_fails_history_after_eval_start() -> None:
    lookups = {
        "GME": _hit("GME", "124739", "GameStop", "2024-09-04"),
        "AVB": _hit("AVB", "1", "AvalonBay", "2024-09-04"),
    }
    proof = evaluate_package_proof(
        ndu_running=True,
        databases=["US Equities"],
        proof_lookups=lookups,
        delisted_match_count=0,
        errors=[],
    )
    assert proof.verdict == STATUS_FAIL


@pytest.mark.unit
def test_package_proof_passes_platinum_depth() -> None:
    lookups = {
        "GME": _hit("GME", "124739", "GameStop", "2002-02-13"),
        "AVB": _hit("AVB", "1", "AvalonBay", "1998-01-02"),
        "ATVI-202310": _hit("ATVI-202310", "99", "Activision Blizzard", "2013-07-08", "2023-10-18"),
    }
    proof = evaluate_package_proof(
        ndu_running=True,
        databases=["US Equities", "US Equities Delisted"],
        proof_lookups=lookups,
        delisted_match_count=0,
        errors=[],
    )
    assert proof.verdict == STATUS_PASS
    assert proof.history_precedes_trial_cap is True
    assert proof.delisted_populated is True
    assert proof.trial_capped is False


@pytest.mark.unit
def test_suffix_discovery_filters_stem_without_dumping_universe() -> None:
    matches = discover_delisted_suffixes(
        "SE",
        ["SE-201702", "SEA-201801", "ATVI-202310", "se-201703", "IGNORE"],
    )
    assert matches == ["SE-201702", "SE-201703"]


@pytest.mark.unit
def test_spectra_occupancy_must_not_use_current_ticker(master) -> None:
    occupancy = Occupancy(
        pit_ticker="SE",
        occupancy_start=date(2007, 1, 3),
        occupancy_end=date(2017, 2, 27),
        expected_identity="Spectra Energy Corp",
        seed_key="spectra-energy",
    )
    assert may_use_current_ticker(occupancy, master) is False


@pytest.mark.unit
def test_gme_may_use_current_ticker_even_if_pit_ended(master) -> None:
    occupancy = Occupancy(
        pit_ticker="GME",
        occupancy_start=date(2007, 12, 14),
        occupancy_end=date(2016, 4, 25),
        expected_identity="GameStop Corp.",
        seed_key="gamestop",
    )
    assert may_use_current_ticker(occupancy, master) is True


@pytest.mark.unit
def test_open_unresolved_occupancy_may_use_current_ticker(master) -> None:
    occupancy = Occupancy(
        pit_ticker="AVB",
        occupancy_start=date(2007, 1, 10),
        occupancy_end=None,
        expected_identity="AvalonBay Communities",
        seed_key=provisional_seed_key("AVB", date(2007, 1, 10), None),
    )
    assert may_use_current_ticker(occupancy, master) is True


@pytest.mark.unit
def test_coverage_trial_start_covers_two_year_window() -> None:
    sample = _sample("GME")
    assert coverage_status_for_dates("2024-09-03", "", sample) == STATUS_PASS
    assert coverage_status_for_dates("2002-02-13", "", sample) == STATUS_PASS


@pytest.mark.unit
def test_coverage_pre_window_occupancy_is_not_testable() -> None:
    sample = _sample("ATVI")
    assert coverage_status_for_dates("2015-08-31", "2023-10-18", sample) == STATUS_NOT_TESTABLE


@pytest.mark.unit
def test_atvi_alias_to_msft_is_fail() -> None:
    sample = _sample("ATVI")
    current = _miss("ATVI")
    suffix = _hit("ATVI-202310", "1", "Microsoft Corporation", "2013-07-08", "2023-10-18")
    suffix.vendor_symbol = "MSFT"
    row = classify_frozen_row(sample, current, suffix)
    assert row.identity_status == STATUS_FAIL
    assert row.verdict == STATUS_FAIL


@pytest.mark.unit
def test_recycle_collapse_marks_spectra_fail() -> None:
    spectra = classify_frozen_row(
        _sample("SE", "2015"),
        _hit("SE", SEA_TRIAL_ASSET_ID, "Sea Limited Class A ADR", "2024-09-03"),
        _hit("SE-201702", SEA_TRIAL_ASSET_ID, "Sea Limited Class A ADR", "2013-07-08", "2017-02-27"),
    )
    sea = classify_frozen_row(
        _sample("SE", "2018"),
        _hit("SE", SEA_TRIAL_ASSET_ID, "Sea Limited Class A ADR", "2017-10-20"),
        _miss(""),
    )
    apply_recycle_identity_rules([spectra, sea])
    assert spectra.identity_status == STATUS_FAIL
    assert spectra.verdict == STATUS_FAIL


@pytest.mark.unit
def test_recycle_safe_distinct_assetids() -> None:
    spectra = classify_frozen_row(
        _sample("SE", "2015"),
        _hit("SE", SEA_TRIAL_ASSET_ID, "Sea Limited Class A ADR", "2017-10-20"),
        _hit("SE-201702", "111", "Spectra Energy Corp", "2007-01-03", "2017-02-27"),
    )
    sea = classify_frozen_row(
        _sample("SE", "2018"),
        _hit("SE", SEA_TRIAL_ASSET_ID, "Sea Limited Class A ADR", "2017-10-20"),
        _miss(""),
    )
    apply_recycle_identity_rules([spectra, sea])
    assert spectra.identity_status == STATUS_PASS
    assert "Recycle-safe" in spectra.notes


@pytest.mark.unit
def test_ticker_change_same_assetid_is_pass() -> None:
    sq = classify_frozen_row(
        _sample("SQ"),
        _miss("SQ"),
        _miss("SQ-202501"),
    )
    xyz = classify_frozen_row(
        _sample("XYZ"),
        _hit("XYZ", "2104402", "Block Inc Class A Common", "2015-11-19"),
        _miss(""),
    )
    # Predecessor mapped via discovered continuity onto the same assetid.
    sq.vendor_security_id = "2104402"
    sq.delisted_asset_id = "2104402"
    matches = compare_ticker_change_pairs([sq, xyz])
    assert matches["SQ->XYZ"] == STATUS_PASS


@pytest.mark.unit
def test_lookup_symbol_records_assetid(fake_client: FakeNorgate) -> None:
    result = lookup_symbol(fake_client, "GME", fetch_bars=False)
    assert result.found is True
    assert result.assetid == "124739"
    assert "GME" in fake_client.symbols_requested


@pytest.mark.unit
def test_build_occupancies_includes_window_members_and_sea_overlay(master) -> None:
    memberships = [
        ConstituentMembership("MSFT", date(1996, 1, 2), None),
        ConstituentMembership("SE", date(2007, 1, 3), date(2017, 2, 27)),
        ConstituentMembership("OLD", date(1996, 1, 2), date(2010, 1, 1)),
    ]
    rows = build_occupancies(memberships, master)
    tickers = {row.pit_ticker for row in rows}
    assert "MSFT" in tickers
    assert "SE" in tickers
    assert "OLD" not in tickers
    sea = [row for row in rows if row.seed_key == "sea-limited"]
    assert sea and sea[0].overlay is True
    spectra = [row for row in rows if row.seed_key == "spectra-energy"]
    assert spectra
    assert all(row.overlay for row in spectra)


@pytest.mark.unit
def test_join_rejects_sea_assetid_for_2016_se(master) -> None:
    occupancy = Occupancy(
        pit_ticker="SE",
        occupancy_start=date(2007, 1, 3),
        occupancy_end=date(2017, 2, 27),
        expected_identity="Spectra Energy Corp",
        seed_key="spectra-energy",
    )
    mapping = OccupancyMapping(occupancy=occupancy)
    mapping.norgate_asset_id = SEA_TRIAL_ASSET_ID
    mapping.identity_source = "current_ticker"
    mapping.mapping_status = "MAPPED"
    memberships = [ConstituentMembership("SE", date(2007, 1, 3), date(2017, 2, 27))]
    gate = gate_j1([mapping], memberships, master, as_of_dates=(date(2016, 1, 4),))
    assert gate.status == STATUS_FAIL
    assert "Sea" in gate.notes or "current ticker" in gate.notes


@pytest.mark.unit
def test_join_in_window_allows_current_sea(master) -> None:
    occupancy = Occupancy(
        pit_ticker="SE",
        occupancy_start=date(2017, 10, 20),
        occupancy_end=None,
        expected_identity="Sea Limited",
        seed_key="sea-limited",
    )
    mapping = OccupancyMapping(occupancy=occupancy)
    mapping.norgate_asset_id = SEA_TRIAL_ASSET_ID
    mapping.identity_source = "current_ticker"
    mapping.mapping_status = "MAPPED"
    memberships = [ConstituentMembership("SE", date(2017, 10, 20), None)]
    gate = gate_j1([mapping], memberships, master, as_of_dates=JOIN_AS_OF_DATES)
    assert gate.status == STATUS_PASS


@pytest.mark.unit
def test_current_ticker_contamination_flag(master) -> None:
    occupancy = Occupancy(
        pit_ticker="SE",
        occupancy_start=date(2007, 1, 3),
        occupancy_end=date(2017, 2, 27),
        expected_identity="Spectra Energy Corp",
        seed_key="spectra-energy",
    )
    mapping = OccupancyMapping(occupancy=occupancy, identity_source="current_ticker")
    assert current_ticker_contamination(mapping, master) is True
    mapping.identity_source = "frozen_suffix"
    assert current_ticker_contamination(mapping, master) is False


@pytest.mark.unit
def test_occupancy_as_of_selects_spectra_not_sea() -> None:
    spectra = OccupancyMapping(
        occupancy=Occupancy("SE", date(2007, 1, 3), date(2017, 2, 27), "Spectra", "spectra-energy")
    )
    sea = OccupancyMapping(
        occupancy=Occupancy("SE", date(2017, 10, 20), None, "Sea Limited", "sea-limited", overlay=True)
    )
    hit = occupancy_for_as_of([spectra, sea], "SE", date(2016, 1, 4))
    assert hit is spectra
    assert occupancy_for_as_of([spectra, sea], "SE", date(2018, 1, 2)) is sea


@pytest.mark.unit
def test_u1_fails_on_current_ticker_contamination(master) -> None:
    occupancy = Occupancy("SE", date(2007, 1, 3), date(2017, 2, 27), "Spectra", "spectra-energy")
    mapping = OccupancyMapping(occupancy=occupancy, identity_source="current_ticker", mapping_status="MAPPED")
    mapping.norgate_asset_id = SEA_TRIAL_ASSET_ID
    gate = gate_u1([mapping], expected_tickers=0, master=master)
    assert gate.status == STATUS_FAIL


@pytest.mark.unit
def test_interior_gap_and_bar_validation(tmp_path: Path) -> None:
    occupancy = Occupancy("GME", date(2013, 7, 8), None, "GameStop", "gamestop")
    bars = [_bar("2013-07-08"), _bar("2013-08-01")]
    gaps = interior_gaps(bars, occupancy)
    assert gaps
    issues = validate_staged_bars([_bar("2013-07-08")], require_adjusted=True)
    assert issues == []
    naive = StagedBar(
        symbol="GME",
        timestamp=datetime(2013, 7, 8),
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        adjusted_close=Decimal("1"),
        volume=1,
    )
    assert validate_staged_bars([naive], require_adjusted=True)
    out = tmp_path / "audit" / "norgate_platinum_trial" / "bars" / "totalreturn" / "124739.csv"
    write_bar_csv(out, [_bar("2013-07-08")])
    assert out.is_file()


@pytest.mark.unit
def test_series_cover_occupancy() -> None:
    occupancy = Occupancy("HOLX", date(2016, 3, 30), date(2026, 4, 9), "Hologic", "hologic")
    bars = [_bar("2016-03-30"), _bar("2025-12-31")]
    assert series_cover_occupancy(bars, occupancy) is True
    assert series_cover_occupancy([_bar("2016-04-01")], occupancy) is False


@pytest.mark.unit
def test_bars_from_timeseries_uses_unadjusted_close_for_totalreturn() -> None:
    payload = [
        {
            "Date": "2013-07-08",
            "Open": "10",
            "High": "11",
            "Low": "9",
            "Close": "12",
            "Unadjusted Close": "6",
            "Volume": "100",
        }
    ]
    bars = bars_from_timeseries("GME", payload, adjusted=True)
    assert len(bars) == 1
    assert bars[0].close == Decimal("6")
    assert bars[0].adjusted_close == Decimal("12")
    assert bars[0].timestamp.tzinfo is not None


@pytest.mark.unit
def test_verdict_research_ready_requires_all_pass_gates() -> None:
    fail = build_verdict([GateResult("F1", STATUS_FAIL, "recycle")])
    assert fail.research_ready is False
    assert fail.norgate_verdict == VERDICT_NOT_SUITABLE

    gates = [
        GateResult("P0", STATUS_PASS),
        GateResult("F1", STATUS_PASS),
        GateResult("F2", STATUS_PASS),
        GateResult("F3", STATUS_PASS),
        GateResult("F4", STATUS_PASS),
        GateResult("U1", STATUS_PASS),
        GateResult("U2", STATUS_PASS),
        GateResult("J1", STATUS_PASS),
        GateResult("M1", STATUS_PASS),
        GateResult("A1", STATUS_PASS),
        GateResult("A2", STATUS_PASS),
        GateResult("I1", STATUS_PASS),
        GateResult("Q1", STATUS_PASS),
    ]
    ok = build_verdict(gates)
    assert ok.norgate_verdict == VERDICT_SUITABLE
    assert ok.vendor_validation_ready is True
    assert ok.project_construction_go is True
    assert ok.full_historical_research_ready is False
    assert ok.research_ready is False
    assert ok.phase_5 == "NOT STARTED"
    assert "unofficial_fja05680_membership" in ok.residuals
    assert "pre_window_delisted_not_testable" in ok.residuals


@pytest.mark.unit
def test_partial_tko_residual_can_be_research_ready() -> None:
    gates = [
        GateResult("P0", STATUS_PASS),
        GateResult("F1", STATUS_PASS),
        GateResult("F2", STATUS_PASS),
        GateResult("F3", STATUS_PASS),
        GateResult("F4", "PARTIAL"),
        GateResult("U1", STATUS_PASS),
        GateResult("U2", STATUS_PASS),
        GateResult("J1", STATUS_PASS),
        GateResult("M1", STATUS_PASS),
        GateResult("A1", STATUS_PASS),
        GateResult("A2", STATUS_PASS),
        GateResult("I1", STATUS_PASS),
        GateResult("Q1", STATUS_PASS),
    ]
    verdict = build_verdict(gates, residuals=["tko_surviving_entity"])
    assert verdict.vendor_validation_ready is True
    assert verdict.project_construction_go is True
    assert verdict.full_historical_research_ready is False
    assert verdict.research_ready is False
    assert verdict.norgate_verdict == "PARTIALLY SUITABLE"


@pytest.mark.unit
def test_gate_p0_and_f1_not_testable_without_artifacts() -> None:
    assert gate_p0(None).status == "NOT_TESTABLE"
    assert gate_f1([]).status == "NOT_TESTABLE"


@pytest.fixture(scope="module")
def master():
    return load_known_identities_catalog()


@pytest.fixture
def fake_client() -> FakeNorgate:
    return FakeNorgate(
        {
            "GME": {
                "assetid": 124739,
                "name": "GameStop Corp Class A Common",
                "first": "2002-02-13",
                "last": "",
            }
        }
    )
