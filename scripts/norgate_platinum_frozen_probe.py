#!/usr/bin/env python3
"""Re-probe the frozen 37-row sample against the 2-year Norgate window.

Reuses FROZEN_SAMPLE from scripts/probe_vendor_coverage.py. Writes only
audit/norgate_platinum_trial/frozen_sample.csv and frozen_sample.json.
Does not modify the existing probe, Trial artifacts, market_bars, or seeds.

Coverage is occupancy ∩ [2024-09-03, 2025-12-31]. Pre-window delists stay
NOT_TESTABLE. Identity/recycle/acquirer rules stay FAIL-closed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.norgate_trial.client import (
    discover_delisted_suffixes,
    empty_lookup,
    load_delisted_symbols,
    lookup_symbol,
)
from app.norgate_trial.frozen import (
    FrozenRow,
    apply_recycle_identity_rules,
    classify_frozen_row,
    compare_ticker_change_pairs,
    frozen_suffix_map,
    rows_payload,
)
from app.norgate_trial.io import read_json, write_csv, write_json
from app.norgate_trial.paths import DEFAULT_OUTPUT_DIR, IsolationError, ensure_layout, trial_layout
from app.norgate_trial.runtime import import_norgatedata, norgate_status
from app.norgate_trial.sample import frozen_sample

LOGGER = logging.getLogger(__name__)

FROZEN_SAMPLE = frozen_sample()

FROZEN_CSV_FIELDS = (
    "sample_category",
    "ticker",
    "historical_period",
    "pit_security",
    "expected_identity",
    "must_not_alias",
    "delisted_suffix",
    "vendor_security_id",
    "vendor_symbol",
    "security_name",
    "first_date",
    "last_date",
    "identity_source",
    "identity_status",
    "coverage_status",
    "verdict",
    "ticker_change_assetid_match",
    "discovered_suffix",
    "current_asset_id",
    "delisted_asset_id",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Frozen 37-row Norgate 2-year window re-probe.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--require-package-proof",
        action="store_true",
        help="Exit if package_proof.json is missing or not PASS.",
    )
    return parser.parse_args()


def _alternate_suffix(
    ticker: str,
    frozen_suffix: str,
    cache: dict[str, list[str]],
    delisted_symbols: list[str] | None,
) -> str:
    if ticker not in cache:
        cache[ticker] = discover_delisted_suffixes(ticker, delisted_symbols or [])
    for symbol in cache[ticker]:
        if symbol != frozen_suffix:
            return symbol
    return ""


def probe_frozen_sample(client: object, *, delisted_db_present: bool) -> tuple[list[FrozenRow], dict[str, str]]:
    delisted_symbols: list[str] | None = None
    discovered_cache: dict[str, list[str]] = {}
    if delisted_db_present:
        delisted_symbols = load_delisted_symbols(client)
        # Keep the full list in memory only for stem filtering.
    rows: list[FrozenRow] = []
    for sample in FROZEN_SAMPLE:
        current = lookup_symbol(client, sample.lookup_ticker or sample.ticker, fetch_bars=True)
        if sample.delisted_suffix and delisted_db_present:
            suffix = lookup_symbol(client, sample.delisted_suffix, fetch_bars=True)
            alternate = _alternate_suffix(
                sample.ticker,
                sample.delisted_suffix,
                discovered_cache,
                delisted_symbols,
            )
            discovered = lookup_symbol(client, alternate, fetch_bars=True) if alternate else empty_lookup("")
        else:
            suffix = empty_lookup(
                sample.delisted_suffix or "",
                "" if not sample.delisted_suffix else "Delisted lookup skipped.",
            )
            discovered = empty_lookup("")
        rows.append(classify_frozen_row(sample, current, suffix, discovered=discovered))
    ticker_change = compare_ticker_change_pairs(rows)
    apply_recycle_identity_rules(rows)
    return rows, ticker_change


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        layout = ensure_layout(trial_layout(args.output_dir))
    except IsolationError as exc:
        raise SystemExit(str(exc)) from exc

    if args.require_package_proof:
        proof = read_json(layout.package_proof)
        if proof.get("verdict") != "PASS":
            raise SystemExit("package_proof.json is missing or not PASS; refuse frozen probe.")

    module, import_error = import_norgatedata()
    extra: dict[str, object] = {
        "frozen_sample_source": "scripts/probe_vendor_coverage.py:FROZEN_SAMPLE",
        "row_count_expected": len(FROZEN_SAMPLE),
        "database_symbols_persisted": False,
    }
    if module is None:
        extra["error"] = import_error
        extra["verdict"] = "NOT_TESTABLE"
        write_json(layout.frozen_json, rows_payload([], extra))
        write_csv(layout.frozen_csv, FROZEN_CSV_FIELDS, [])
        LOGGER.error("norgatedata unavailable: %s", import_error)
        return 2

    running, databases, errors = norgate_status(module)
    extra["ndu_running"] = running
    extra["databases"] = databases
    extra["errors"] = errors
    if not running:
        extra["verdict"] = "NOT_TESTABLE"
        write_json(layout.frozen_json, rows_payload([], extra))
        write_csv(layout.frozen_csv, FROZEN_CSV_FIELDS, [])
        LOGGER.error("NDU is not running.")
        return 2

    delisted = any(name.casefold() == "us equities delisted" for name in databases)
    rows, ticker_change = probe_frozen_sample(module, delisted_db_present=delisted)
    extra["ticker_change_assetid_match"] = ticker_change
    extra["suffix_map"] = frozen_suffix_map(list(FROZEN_SAMPLE))
    extra["delisted_db_present"] = delisted
    write_csv(layout.frozen_csv, FROZEN_CSV_FIELDS, [row.as_csv_dict() for row in rows])
    write_json(layout.frozen_json, rows_payload(rows, extra))
    LOGGER.info("Wrote %s (%s rows)", layout.frozen_csv, len(rows))
    fails = sum(1 for row in rows if row.verdict == "FAIL")
    if fails:
        LOGGER.error("Frozen sample has %s FAIL rows.", fails)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
