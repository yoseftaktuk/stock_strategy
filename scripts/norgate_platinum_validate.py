#!/usr/bin/env python3
"""Validate staged 2-year Norgate trial artifacts and write verdict.json.

Does not promote into market_bars. Does not start Strategy Research.
Vendor Validation Ready is the construction GO gate. Full Historical
Research Ready stays NO until a future Platinum trial.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.norgate_trial.bars import read_bar_csv, validate_staged_bars
from app.norgate_trial.client import PackageProof, parse_iso_date
from app.norgate_trial.constants import JOIN_AS_OF_DATES, OCCUPANCY_CSV_FIELDS
from app.norgate_trial.frozen import FrozenRow
from app.norgate_trial.io import read_csv, read_json, write_csv, write_json
from app.norgate_trial.occupancy import Occupancy, OccupancyMapping, window_ticker_count
from app.norgate_trial.paths import DEFAULT_OUTPUT_DIR, IsolationError, ensure_layout, trial_layout
from app.norgate_trial.runtime import import_norgatedata, norgate_status
from app.norgate_trial.validation import (
    build_verdict,
    gate_a1,
    gate_a2,
    gate_f1,
    gate_f2,
    gate_f3,
    gate_f4,
    gate_i1,
    gate_j1,
    gate_m1,
    gate_p0,
    gate_q1,
    gate_u1,
    gate_u2,
)
from app.security_master.seed import load_known_identities_catalog
from app.universe.exceptions import UniverseSourceError
from app.universe.memory import InMemoryUniverseProvider
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Norgate 2-year vendor-validation artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-file", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument(
        "--expected-tickers",
        type=int,
        default=0,
        help="Unique PIT tickers overlapping 2024-09-03→2025-12-31 (0 = derive from occupancy map).",
    )
    parser.add_argument(
        "--skip-spx-crosscheck",
        action="store_true",
        help="Do not call index_constituent_timeseries.",
    )
    return parser.parse_args()


def _package_proof(raw: dict[str, object]) -> PackageProof | None:
    if not raw:
        return None
    proof = PackageProof()
    proof.ndu_running = bool(raw.get("ndu_running"))
    proof.norgatedata_importable = bool(raw.get("norgatedata_importable"))
    databases = raw.get("databases")
    proof.databases = [str(item) for item in databases] if isinstance(databases, list) else []
    proof.delisted_db_present = bool(raw.get("delisted_db_present"))
    proof.listed_db_present = bool(raw.get("listed_db_present"))
    proof.delisted_populated = bool(raw.get("delisted_populated"))
    proof.history_precedes_trial_cap = bool(raw.get("history_precedes_trial_cap"))
    proof.trial_capped = bool(raw.get("trial_capped"))
    proof.verdict = str(raw.get("verdict") or "NOT_TESTABLE")
    proof.notes = str(raw.get("notes") or "")
    return proof


def _frozen_rows(raw_rows: list[dict[str, str]]) -> list[FrozenRow]:
    rows: list[FrozenRow] = []
    for item in raw_rows:
        rows.append(
            FrozenRow(
                sample_category=item.get("sample_category", ""),
                ticker=item.get("ticker", ""),
                historical_period=item.get("historical_period", ""),
                pit_security=item.get("pit_security", ""),
                expected_identity=item.get("expected_identity", ""),
                security_valid_from=item.get("security_valid_from", ""),
                security_valid_to=item.get("security_valid_to", ""),
                must_not_alias=item.get("must_not_alias", ""),
                delisted_suffix=item.get("delisted_suffix", ""),
                vendor_security_id=item.get("vendor_security_id", ""),
                vendor_symbol=item.get("vendor_symbol", ""),
                security_name=item.get("security_name", ""),
                first_date=item.get("first_date", ""),
                last_date=item.get("last_date", ""),
                identity_source=item.get("identity_source", ""),
                identity_status=item.get("identity_status", "NOT_TESTABLE"),
                coverage_status=item.get("coverage_status", "NOT_TESTABLE"),
                verdict=item.get("verdict", "NOT_TESTABLE"),
                ticker_change_assetid_match=item.get("ticker_change_assetid_match", ""),
                discovered_suffix=item.get("discovered_suffix", ""),
                current_asset_id=item.get("current_asset_id", ""),
                delisted_asset_id=item.get("delisted_asset_id", ""),
                notes=item.get("notes", ""),
            )
        )
    return rows


def _occupancy_mappings(raw_rows: list[dict[str, str]]) -> list[OccupancyMapping]:
    mappings: list[OccupancyMapping] = []
    for item in raw_rows:
        start = parse_iso_date(item.get("occupancy_start") or "")
        if start is None:
            continue
        end = parse_iso_date(item.get("occupancy_end") or "")
        occupancy = Occupancy(
            pit_ticker=item.get("pit_ticker") or "",
            occupancy_start=start,
            occupancy_end=end,
            expected_identity=item.get("expected_identity") or "",
            seed_key=item.get("seed_key") or "",
            overlay="overlay occupancy" in (item.get("notes") or ""),
        )
        mapping = OccupancyMapping(occupancy=occupancy)
        mapping.norgate_symbol = item.get("norgate_symbol") or ""
        mapping.norgate_asset_id = item.get("norgate_asset_id") or ""
        mapping.security_name = item.get("security_name") or ""
        mapping.first_quoted = item.get("first_quoted") or ""
        mapping.last_quoted = item.get("last_quoted") or ""
        mapping.identity_source = item.get("identity_source") or ""
        mapping.mapping_status = item.get("mapping_status") or "UNRESOLVED"
        mapping.notes = item.get("notes") or ""
        mappings.append(mapping)
    return mappings


def _load_bars(layout_dir: Path) -> dict[str, list]:
    bars: dict[str, list] = {}
    if not layout_dir.is_dir():
        return bars
    for path in sorted(layout_dir.glob("*.csv")):
        bars[path.stem] = read_bar_csv(path)
    return bars


def _spx_crosscheck(
    memberships: list,
    as_of_dates: tuple[date, ...],
    *,
    skip: bool,
) -> tuple[list[dict[str, str]], bool | None]:
    if skip:
        return [], None
    module, _error = import_norgatedata()
    if module is None:
        return [], False
    running, _databases, _errors = norgate_status(module)
    if not running:
        return [], False
    fn = getattr(module, "index_constituent_timeseries", None)
    if not callable(fn):
        return [], False
    provider = InMemoryUniverseProvider(memberships)
    rows: list[dict[str, str]] = []
    for as_of in as_of_dates:
        pit = set(provider.get_symbols(as_of))
        norgate_members: set[str] = set()
        for symbol in sorted(pit):
            try:
                series = fn(symbol, "$SPX", start_date=as_of.isoformat(), end_date=as_of.isoformat())
            except Exception:  # noqa: BLE001
                try:
                    series = fn(symbol, "S&P 500", start_date=as_of.isoformat(), end_date=as_of.isoformat())
                except Exception:  # noqa: BLE001
                    continue
            if _constituent_on(series, as_of):
                norgate_members.add(symbol)
        only_pit = sorted(pit - norgate_members)
        only_norgate = sorted(norgate_members - pit)
        rows.append(
            {
                "as_of": as_of.isoformat(),
                "pit_count": str(len(pit)),
                "norgate_count": str(len(norgate_members)),
                "only_pit": ",".join(only_pit[:50]),
                "only_norgate": ",".join(only_norgate[:50]),
                "disagreement_count": str(len(only_pit) + len(only_norgate)),
            }
        )
    return rows, True


def _constituent_on(series: object, as_of: date) -> bool:
    if series is None:
        return False
    if isinstance(series, list) and series:
        return True
    flag = getattr(series, "empty", None)
    if flag is True:
        return False
    values = getattr(series, "values", None)
    if values is not None:
        try:
            return any(bool(item) for item in list(values))
        except TypeError:
            return False
    return bool(series)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        layout = ensure_layout(trial_layout(args.output_dir))
    except IsolationError as exc:
        raise SystemExit(str(exc)) from exc

    proof = _package_proof(read_json(layout.package_proof))
    frozen = _frozen_rows(read_csv(layout.frozen_csv))
    frozen_json = read_json(layout.frozen_json)
    ticker_change = frozen_json.get("ticker_change_assetid_match")
    if not isinstance(ticker_change, dict):
        ticker_change = {row.ticker: row.ticker_change_assetid_match for row in frozen if row.ticker_change_assetid_match}

    mappings = _occupancy_mappings(read_csv(layout.occupancy))
    totalreturn = _load_bars(layout.totalreturn_dir)
    unadjusted = _load_bars(layout.unadjusted_dir)
    sample_tr: list = []
    sample_raw: list = []
    if totalreturn:
        key = next(iter(totalreturn))
        sample_tr = totalreturn[key]
        sample_raw = unadjusted.get(key, [])

    try:
        loaded = SP500HistoricalSource().load(source_file=args.source_file)
        memberships = list(loaded.memberships)
    except UniverseSourceError as exc:
        LOGGER.warning("Could not load PIT source for join snapshots: %s", exc)
        memberships = []

    master = load_known_identities_catalog()
    crosscheck, spx_available = _spx_crosscheck(
        memberships,
        JOIN_AS_OF_DATES,
        skip=args.skip_spx_crosscheck,
    )
    if crosscheck:
        write_csv(
            layout.membership_crosscheck,
            ("as_of", "pit_count", "norgate_count", "only_pit", "only_norgate", "disagreement_count"),
            crosscheck,
        )

    q1_issues: list[str] = []
    for assetid, bars in totalreturn.items():
        q1_issues.extend(validate_staged_bars(bars, require_adjusted=True))
        if q1_issues:
            q1_issues = [f"{assetid}: {q1_issues[0]}"]
            break

    expected_tickers = args.expected_tickers or window_ticker_count(
        [row.occupancy for row in mappings]
    )
    gates = [
        gate_p0(proof),
        gate_f1(frozen),
        gate_f2(frozen),
        gate_f3({str(key): str(value) for key, value in ticker_change.items()}),
        gate_f4(frozen),
        gate_u1(mappings, expected_tickers=expected_tickers, master=master),
        gate_u2(mappings, totalreturn),
        gate_j1(mappings, memberships, master),
        gate_m1(len(crosscheck), spx_available),
        gate_a1(sample_tr, sample_raw),
        gate_a2(sample_tr, sample_raw),
        gate_i1(production_modified=False),
        gate_q1(q1_issues),
    ]
    residuals = ["unofficial_fja05680_membership"]
    if any(gate.gate_id == "F4" and gate.status == "PARTIAL" for gate in gates):
        residuals.append("tko_surviving_entity")
    verdict = build_verdict(gates, residuals=residuals)

    write_csv(layout.frozen_matrix, tuple(frozen[0].as_csv_dict().keys()) if frozen else ("ticker",), [row.as_csv_dict() for row in frozen])
    write_csv(
        layout.pit_coverage,
        OCCUPANCY_CSV_FIELDS,
        [row.as_csv_dict() for row in mappings],
    )
    write_csv(
        layout.identity_gates,
        ("gate_id", "status", "notes"),
        [gate.as_csv_dict() for gate in gates],
    )
    write_csv(
        layout.adjustment_checks,
        ("gate_id", "status", "notes"),
        [gate.as_csv_dict() for gate in gates if gate.gate_id in {"A1", "A2", "Q1"}],
    )
    payload = verdict.as_dict()
    payload["research_ready"] = False
    payload["vendor_validation_ready"] = bool(verdict.vendor_validation_ready)
    payload["project_construction_go"] = bool(verdict.project_construction_go)
    payload["full_historical_research_ready"] = False
    payload["phase_5"] = "NOT STARTED"
    payload["promotion"] = "FORBIDDEN"
    write_json(layout.verdict, payload)
    LOGGER.info("Wrote %s", layout.verdict)
    LOGGER.info(
        "Norgate verdict: %s vendor_validation_ready=%s construction_go=%s",
        verdict.norgate_verdict,
        verdict.vendor_validation_ready,
        verdict.project_construction_go,
    )
    return 0 if verdict.norgate_verdict != "NOT_TESTABLE" else 2


if __name__ == "__main__":
    sys.exit(main())
