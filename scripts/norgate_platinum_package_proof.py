#!/usr/bin/env python3
"""Prove the local NDU database covers the 2-year vendor-validation window.

Writes audit/norgate_platinum_trial/package_proof.json only. Does not write
market_bars, Security Master seeds, data/raw, or Trial artifacts.

Trial-depth history beginning 2024-09-03 is the expected PASS for this gate.
Populated historical Delisted is not required. Full Historical Research Ready
remains a future Platinum gate.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.norgate_trial.client import (
    LookupResult,
    evaluate_package_proof,
    load_delisted_symbols,
    lookup_symbol,
)
from app.norgate_trial.constants import (
    DELISTED_PROBE_SUFFIXES,
    PACKAGE_PROOF_SYMBOLS,
)
from app.norgate_trial.io import environment_payload, write_json
from app.norgate_trial.paths import DEFAULT_OUTPUT_DIR, IsolationError, ensure_layout, trial_layout
from app.norgate_trial.runtime import import_norgatedata, norgate_status

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove Norgate 2-year Trial depth without exporting the US tape."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Isolated Platinum trial directory (default: audit/norgate_platinum_trial).",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        layout = ensure_layout(trial_layout(args.output_dir))
    except IsolationError as exc:
        raise SystemExit(str(exc)) from exc

    module, import_error = import_norgatedata()
    lookups: dict[str, LookupResult] = {}
    errors: list[str] = []
    databases: list[str] = []
    running = False
    delisted_match_count = 0
    if module is None:
        errors.append(import_error or "norgatedata is not importable.")
        proof = evaluate_package_proof(
            ndu_running=False,
            databases=[],
            proof_lookups={},
            delisted_match_count=0,
            errors=errors,
            norgatedata_importable=False,
        )
    else:
        running, databases, status_errors = norgate_status(module)
        errors.extend(status_errors)
        if running:
            for symbol in (*PACKAGE_PROOF_SYMBOLS, *DELISTED_PROBE_SUFFIXES):
                lookups[symbol] = lookup_symbol(module, symbol, fetch_bars=False)
            # Count Delisted stem matches in memory; do not persist the full list.
            delisted_symbols = load_delisted_symbols(module)
            delisted_match_count = len(delisted_symbols)
        proof = evaluate_package_proof(
            ndu_running=running,
            databases=databases,
            proof_lookups=lookups,
            delisted_match_count=delisted_match_count,
            errors=errors,
            norgatedata_importable=True,
        )

    write_json(layout.package_proof, proof.as_dict())
    write_json(
        layout.environment,
        environment_payload(
            extra={
                "norgatedata_importable": proof.norgatedata_importable,
                "ndu_running": proof.ndu_running,
                "databases": proof.databases,
                "package_proof_verdict": proof.verdict,
            }
        ),
    )
    LOGGER.info("Wrote %s", layout.package_proof)
    LOGGER.info("Package proof verdict: %s", proof.verdict)
    if proof.verdict != "PASS":
        LOGGER.error("%s", proof.notes)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
