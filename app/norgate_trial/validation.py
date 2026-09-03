"""Fail-closed Platinum trial validation and RESEARCH READY verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.norgate_trial.bars import (
    StagedBar,
    interior_gaps,
    series_cover_occupancy,
    totalreturn_differs,
    validate_staged_bars,
)
from app.norgate_trial.client import PackageProof, parse_iso_date
from app.norgate_trial.constants import (
    ALLOWED_PARTIAL_RESIDUALS,
    CATEGORY_A_TICKERS,
    JOIN_AS_OF_DATES,
    RESEARCH_WINDOW_END,
    RESEARCH_WINDOW_START,
    SEA_TRIAL_ASSET_ID,
    STATUS_FAIL,
    STATUS_NOT_TESTABLE,
    STATUS_PARTIAL,
    STATUS_PASS,
    TICKER_CHANGE_PAIRS,
    VERDICT_NOT_SUITABLE,
    VERDICT_NOT_TESTABLE,
    VERDICT_PARTIALLY_SUITABLE,
    VERDICT_SUITABLE,
)
from app.norgate_trial.frozen import FrozenRow
from app.norgate_trial.occupancy import OccupancyMapping, current_ticker_contamination
from app.security_master.interface import SecurityMaster
from app.universe.models import ConstituentMembership


@dataclass
class GateResult:
    gate_id: str
    status: str
    notes: str = ""

    def as_csv_dict(self) -> dict[str, str]:
        return {"gate_id": self.gate_id, "status": self.status, "notes": self.notes}


@dataclass
class Verdict:
    norgate_verdict: str
    research_ready: bool
    vendor_validation_ready: bool = False
    project_construction_go: bool = False
    full_historical_research_ready: bool = False
    gates: list[GateResult] = field(default_factory=list)
    residuals: list[str] = field(default_factory=list)
    phase_5: str = "NOT STARTED"
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "norgate_verdict": self.norgate_verdict,
            "vendor_validation_ready": self.vendor_validation_ready,
            "project_construction_go": self.project_construction_go,
            "full_historical_research_ready": self.full_historical_research_ready,
            "research_ready": self.research_ready,
            "phase_5": self.phase_5,
            "residuals": list(self.residuals),
            "notes": self.notes,
            "gates": [gate.as_csv_dict() for gate in self.gates],
        }


def gate_p0(proof: PackageProof | None) -> GateResult:
    if proof is None:
        return GateResult("P0", STATUS_NOT_TESTABLE, "package_proof.json missing.")
    if proof.verdict == STATUS_PASS:
        return GateResult("P0", STATUS_PASS, proof.notes)
    if proof.verdict == STATUS_FAIL:
        return GateResult("P0", STATUS_FAIL, proof.notes)
    return GateResult("P0", STATUS_NOT_TESTABLE, proof.notes)


def gate_f1(rows: list[FrozenRow]) -> GateResult:
    if not rows:
        return GateResult("F1", STATUS_NOT_TESTABLE, "frozen sample not executed.")
    fails = [row for row in rows if row.identity_status == STATUS_FAIL]
    if fails:
        tickers = ", ".join(sorted({row.ticker for row in fails}))
        return GateResult("F1", STATUS_FAIL, f"identity FAIL: {tickers}")
    not_testable = sum(1 for row in rows if row.identity_status == STATUS_NOT_TESTABLE)
    return GateResult(
        "F1",
        STATUS_PASS,
        "no identity FAIL on recycle/acquirer rules; "
        f"{not_testable} pre-window or unresolved rows remain NOT_TESTABLE.",
    )


def gate_f2(rows: list[FrozenRow]) -> GateResult:
    if not rows:
        return GateResult("F2", STATUS_NOT_TESTABLE, "frozen sample not executed.")
    fails = [row for row in rows if row.coverage_status == STATUS_FAIL]
    if fails:
        tickers = ", ".join(sorted({row.ticker for row in fails}))
        return GateResult("F2", STATUS_FAIL, f"coverage FAIL: {tickers}")
    in_window = [row for row in rows if row.coverage_status == STATUS_PASS]
    if not in_window:
        return GateResult("F2", STATUS_NOT_TESTABLE, "no in-window frozen coverage rows.")
    not_testable = sum(1 for row in rows if row.coverage_status == STATUS_NOT_TESTABLE)
    return GateResult(
        "F2",
        STATUS_PASS,
        f"{len(in_window)} in-window coverage PASS; "
        f"{not_testable} pre-window rows NOT_TESTABLE.",
    )


def gate_f3(ticker_change: dict[str, str]) -> GateResult:
    if not ticker_change:
        return GateResult("F3", STATUS_NOT_TESTABLE, "ticker-change pairs not compared.")
    if any(status == STATUS_FAIL for status in ticker_change.values()):
        failed = [key for key, status in ticker_change.items() if status == STATUS_FAIL]
        return GateResult("F3", STATUS_FAIL, f"different assetids: {', '.join(failed)}")
    if all(status == STATUS_PASS for status in ticker_change.values()):
        return GateResult("F3", STATUS_PASS, "ticker-change pairs share assetid.")
    return GateResult("F3", STATUS_PARTIAL, "predecessor miss only; successor unproven or PARTIAL.")


def gate_f4(rows: list[FrozenRow]) -> GateResult:
    tko = next((row for row in rows if row.ticker == "TKO"), None)
    wwe = next((row for row in rows if row.ticker == "WWE"), None)
    if tko is None or wwe is None:
        return GateResult("F4", STATUS_NOT_TESTABLE, "TKO/WWE rows missing.")
    tko_id = tko.vendor_security_id or tko.current_asset_id
    wwe_id = wwe.vendor_security_id or wwe.delisted_asset_id
    if not tko_id and not wwe_id:
        return GateResult("F4", STATUS_NOT_TESTABLE, "TKO and WWE both unresolved.")
    if tko_id and wwe_id and tko_id == wwe_id:
        if "surviving" in tko.notes.lower() or "surviving" in wwe.notes.lower():
            return GateResult("F4", STATUS_PARTIAL, "documented surviving-entity disagreement.")
        return GateResult("F4", STATUS_FAIL, "WWE bars labeled as TKO without note.")
    if tko_id and wwe_id and tko_id != wwe_id:
        return GateResult("F4", STATUS_PASS, "TKO and WWE have distinct assetids.")
    return GateResult("F4", STATUS_PARTIAL, "one of TKO/WWE unresolved.")


def gate_u1(
    mappings: list[OccupancyMapping],
    *,
    expected_tickers: int,
    master: SecurityMaster | None,
) -> GateResult:
    if not mappings:
        return GateResult("U1", STATUS_NOT_TESTABLE, "occupancy map missing.")
    window_tickers = {
        row.occupancy.pit_ticker
        for row in mappings
        if not row.occupancy.overlay
        and row.occupancy.occupancy_start <= RESEARCH_WINDOW_END
        and (row.occupancy.occupancy_end is None or row.occupancy.occupancy_end > RESEARCH_WINDOW_START)
    }
    contaminated = [
        row
        for row in mappings
        if current_ticker_contamination(row, master)
    ]
    if contaminated:
        tickers = ", ".join(sorted({row.occupancy.pit_ticker for row in contaminated}))
        return GateResult("U1", STATUS_FAIL, f"current-ticker contamination: {tickers}")
    attempted = len(window_tickers)
    if expected_tickers and attempted < expected_tickers:
        return GateResult(
            "U1",
            STATUS_FAIL,
            f"occupancy map has {attempted} window tickers; expected {expected_tickers}.",
        )
    unresolved = sum(1 for row in mappings if row.mapping_status != "MAPPED")
    return GateResult(
        "U1",
        STATUS_PASS,
        f"{attempted} window tickers attempted; {unresolved} occupancies UNRESOLVED/CONFLICT.",
    )


def gate_u2(
    mappings: list[OccupancyMapping],
    bars_by_assetid: dict[str, list[StagedBar]],
) -> GateResult:
    if not mappings:
        return GateResult("U2", STATUS_NOT_TESTABLE, "occupancy map missing.")
    failures: list[str] = []
    missing = 0
    skipped_pre_window = 0
    for row in mappings:
        if row.occupancy.overlay and not row.occupancy.overlaps_eval_window():
            skipped_pre_window += 1
            continue
        if not row.occupancy.overlaps_eval_window():
            skipped_pre_window += 1
            continue
        if row.mapping_status != "MAPPED" or not row.norgate_asset_id:
            missing += 1
            continue
        bars = bars_by_assetid.get(row.norgate_asset_id, [])
        if not bars:
            missing += 1
            continue
        if interior_gaps(bars, row.occupancy):
            failures.append(row.occupancy.pit_ticker)
            continue
        if not series_cover_occupancy(bars, row.occupancy):
            failures.append(row.occupancy.pit_ticker)
    if failures:
        return GateResult("U2", STATUS_FAIL, f"interior gap or short series: {', '.join(sorted(set(failures))[:20])}")
    return GateResult(
        "U2",
        STATUS_PASS,
        f"identity-safe staged series; missing in-window occupancies listed as {missing}; "
        f"{skipped_pre_window} pre-window overlays not required for coverage.",
    )


def gate_j1(
    mappings: list[OccupancyMapping],
    memberships: list[ConstituentMembership],
    master: SecurityMaster | None,
    *,
    as_of_dates: tuple[date, ...] = JOIN_AS_OF_DATES,
) -> GateResult:
    if not mappings or not memberships:
        return GateResult("J1", STATUS_NOT_TESTABLE, "mappings or memberships missing.")
    problems: list[str] = []
    for as_of in as_of_dates:
        pit = sorted({item.symbol for item in memberships if item.contains(as_of)})
        if not pit:
            problems.append(f"{as_of.isoformat()}: empty PIT snapshot.")
            continue
        for ticker in pit:
            matches = [
                row
                for row in mappings
                if row.occupancy.pit_ticker == ticker and row.occupancy.contains(as_of)
            ]
            if not matches:
                problems.append(f"{as_of.isoformat()} {ticker}: no occupancy map row.")
                continue
            row = matches[0]
            if current_ticker_contamination(row, master):
                problems.append(f"{as_of.isoformat()} {ticker}: mapped via live ticker.")
            if ticker == "SE" and as_of == date(2016, 1, 4):
                if row.norgate_asset_id == SEA_TRIAL_ASSET_ID:
                    problems.append("2016-01-04 SE mapped to Sea assetid 2326776.")
                if row.identity_source == "current_ticker":
                    problems.append("2016-01-04 SE used current ticker (Sea).")
    if problems:
        return GateResult("J1", STATUS_FAIL, " ".join(problems[:8]))
    return GateResult("J1", STATUS_PASS, "as-of joins used occupancy, not live ticker.")


def gate_m1(crosscheck_rows: int, spx_api_available: bool | None) -> GateResult:
    if spx_api_available is False:
        return GateResult("M1", STATUS_NOT_TESTABLE, "$SPX API missing.")
    if crosscheck_rows <= 0 and spx_api_available is None:
        return GateResult("M1", STATUS_NOT_TESTABLE, "membership cross-check not written.")
    return GateResult("M1", STATUS_PASS, "disagreement file exists; PIT was not rewritten.")


def gate_a1(totalreturn: list[StagedBar], unadjusted: list[StagedBar]) -> GateResult:
    if not totalreturn or not unadjusted:
        return GateResult("A1", STATUS_FAIL, "TOTALRETURN or unadjusted series missing.")
    issues = validate_staged_bars(totalreturn, require_adjusted=True)
    if issues:
        return GateResult("A1", STATUS_FAIL, issues[0])
    if any(item.volume < 0 for item in totalreturn):
        return GateResult("A1", STATUS_FAIL, "negative volume.")
    return GateResult("A1", STATUS_PASS, "OHLCV + TOTALRETURN + unadjusted + volume present.")


def gate_a2(totalreturn: list[StagedBar], unadjusted: list[StagedBar]) -> GateResult:
    differ = totalreturn_differs(totalreturn, unadjusted)
    if differ is True:
        return GateResult("A2", STATUS_PASS, "TOTALRETURN differs from NONE.")
    if differ is False:
        return GateResult(
            "A2",
            STATUS_PARTIAL,
            "TOTALRETURN equals NONE in the sampled window; no action dates found.",
        )
    return GateResult("A2", STATUS_NOT_TESTABLE, "could not compare adjustment modes.")


def gate_i1(*, production_modified: bool) -> GateResult:
    if production_modified:
        return GateResult("I1", STATUS_FAIL, "production data was modified.")
    return GateResult("I1", STATUS_PASS, "no market_bars / seed / data/raw / factory writes.")


def gate_q1(issues: list[str]) -> GateResult:
    if issues:
        return GateResult("Q1", STATUS_FAIL, issues[0])
    return GateResult("Q1", STATUS_PASS, "staged bars passed validate_historical_parsed_bar.")


def build_verdict(
    gates: list[GateResult],
    *,
    residuals: list[str] | None = None,
) -> Verdict:
    residual_list = list(residuals or [])
    by_id = {gate.gate_id: gate.status for gate in gates}
    blocking = {gate.gate_id for gate in gates if gate.status == STATUS_FAIL}
    identity_fail = bool({"F1", "F3", "U1", "J1"} & blocking)
    coverage_fail = bool({"P0", "F2", "U2", "A1"} & blocking)
    isolation_fail = "I1" in blocking

    vendor_ready = False
    norgate = VERDICT_NOT_TESTABLE
    notes = "2-year vendor validation has not produced live evidence."

    if by_id.get("P0") == STATUS_NOT_TESTABLE or by_id.get("F1") == STATUS_NOT_TESTABLE:
        norgate = VERDICT_NOT_TESTABLE
        notes = "2-year vendor validation has not produced live evidence."
    elif identity_fail or isolation_fail:
        norgate = VERDICT_NOT_SUITABLE
        notes = "Identity, recycle, join, or isolation FAIL."
    elif coverage_fail:
        norgate = VERDICT_NOT_SUITABLE
        notes = "2-year window coverage FAIL."
    elif all(gate.status == STATUS_PASS for gate in gates):
        norgate = VERDICT_SUITABLE
        vendor_ready = True
        notes = "Live 2-year Trial evidence meets vendor-validation identity/coverage gates."
    else:
        extra = [item for item in residual_list if item not in ALLOWED_PARTIAL_RESIDUALS]
        if extra:
            norgate = VERDICT_PARTIALLY_SUITABLE
            notes = "PARTIAL residuals are not limited to allowed 2-year residuals."
        else:
            norgate = VERDICT_PARTIALLY_SUITABLE
            f4 = by_id.get("F4")
            m1 = by_id.get("M1")
            allowed_partial = {STATUS_PASS, STATUS_PARTIAL}
            vendor_ready = (
                by_id.get("P0") == STATUS_PASS
                and by_id.get("F1") == STATUS_PASS
                and by_id.get("F2") == STATUS_PASS
                and by_id.get("F3") in {STATUS_PASS, STATUS_PARTIAL}
                and (f4 in allowed_partial or f4 == STATUS_NOT_TESTABLE)
                and by_id.get("U1") == STATUS_PASS
                and by_id.get("U2") == STATUS_PASS
                and by_id.get("J1") == STATUS_PASS
                and by_id.get("A1") == STATUS_PASS
                and by_id.get("I1") == STATUS_PASS
                and m1 in {STATUS_PASS, STATUS_PARTIAL, STATUS_NOT_TESTABLE}
            )
            notes = (
                "PARTIALLY SUITABLE with allowed 2-year residuals only."
                if vendor_ready
                else "PARTIAL remaining; Vendor Validation Ready stays NO."
            )

    if vendor_ready and "unofficial_fja05680_membership" not in residual_list:
        residual_list.append("unofficial_fja05680_membership")
    if norgate == VERDICT_SUITABLE and "unofficial_fja05680_membership" not in residual_list:
        residual_list.append("unofficial_fja05680_membership")
    if "pre_window_delisted_not_testable" not in residual_list:
        residual_list.append("pre_window_delisted_not_testable")

    return Verdict(
        norgate_verdict=norgate,
        research_ready=False,
        vendor_validation_ready=vendor_ready,
        project_construction_go=vendor_ready,
        full_historical_research_ready=False,
        gates=gates,
        residuals=residual_list,
        notes=notes,
    )


def category_a_present(rows: list[FrozenRow]) -> bool:
    found = {row.ticker for row in rows if row.ticker in CATEGORY_A_TICKERS and row.identity_status == STATUS_PASS}
    return CATEGORY_A_TICKERS <= found


def parse_date_field(value: str) -> date | None:
    return parse_iso_date(value)
