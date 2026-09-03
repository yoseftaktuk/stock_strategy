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
import json
import logging
import sys
import time
from pathlib import Path

# #region agent log
def _debug_log_import_path() -> None:
    root = Path(__file__).resolve().parents[1]
    app_dir = root / "app"
    payload = {
        "sessionId": "f8992d",
        "runId": "pre-fix",
        "hypothesisId": "A",
        "location": "scripts/norgate_platinum_package_proof.py:import",
        "message": "script import path before app import",
        "timestamp": int(time.time() * 1000),
        "data": {
            "cwd": str(Path.cwd()),
            "file": str(Path(__file__).resolve()),
            "repo_root": str(root),
            "app_dir_exists": app_dir.is_dir(),
            "sys_path0": sys.path[0] if sys.path else "",
            "sys_path": sys.path[:8],
            "pythonpath": __import__("os").environ.get("PYTHONPATH", ""),
            "app_in_sys_path": any(Path(item).resolve() == root for item in sys.path if item),
        },
    }
    line = json.dumps(payload) + "\n"
    print(f"DEBUG_IMPORT_PATH {json.dumps(payload['data'])}", flush=True)
    for candidate in (
        Path("/Users/natankatz/stock_stategy/.cursor/debug-f8992d.log"),
        root / ".cursor" / "debug-f8992d.log",
    ):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            continue


_debug_log_import_path()
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# #region agent log
_post = {
    "sessionId": "f8992d",
    "runId": "post-fix",
    "hypothesisId": "A",
    "location": "scripts/norgate_platinum_package_proof.py:sys_path_insert",
    "message": "repo root inserted on sys.path",
    "timestamp": int(time.time() * 1000),
    "data": {
        "sys_path0": sys.path[0] if sys.path else "",
        "app_in_sys_path": any(Path(item).resolve() == _ROOT for item in sys.path if item),
        "app_dir_exists": (_ROOT / "app").is_dir(),
    },
}
print(f"DEBUG_IMPORT_PATH_AFTER {json.dumps(_post['data'])}", flush=True)
for _candidate in (
    Path("/Users/natankatz/stock_stategy/.cursor/debug-f8992d.log"),
    _ROOT / ".cursor" / "debug-f8992d.log",
):
    try:
        _candidate.parent.mkdir(parents=True, exist_ok=True)
        with _candidate.open("a", encoding="utf-8") as _handle:
            _handle.write(json.dumps(_post) + "\n")
    except OSError:
        continue
# #endregion

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
