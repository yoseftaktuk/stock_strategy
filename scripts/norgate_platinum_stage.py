#!/usr/bin/env python3
"""Stage PIT occupancies and bounded Norgate bars under assetid.

Reads fja05680 membership and Security Master seeds read-only. Writes only
audit/norgate_platinum_trial/mapping and bars. Does not touch market_bars,
data/raw, or production seeds.

Official window: 2024-09-03 → 2025-12-31. Pre-window identity overlays are
mapped for recycle/acquirer checks; their bars are not required for coverage.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.norgate_trial.bars import bars_from_timeseries, clip_to_occupancy, write_bar_csv
from app.norgate_trial.client import discover_delisted_suffixes, load_delisted_symbols, price_timeseries
from app.norgate_trial.constants import OCCUPANCY_CSV_FIELDS
from app.norgate_trial.frozen import frozen_suffix_map
from app.norgate_trial.io import write_csv
from app.norgate_trial.occupancy import (
    OccupancyMapping,
    build_occupancies,
    map_occupancy,
    successor_for,
)
from app.norgate_trial.paths import (
    DEFAULT_OUTPUT_DIR,
    IsolationError,
    ensure_layout,
    trial_layout,
)
from app.norgate_trial.runtime import import_norgatedata, norgate_status
from app.security_master.seed import load_known_identities_catalog
from app.universe.exceptions import UniverseSourceError
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource
from app.norgate_trial.sample import frozen_sample

LOGGER = logging.getLogger(__name__)

FROZEN_SAMPLE = frozen_sample()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage Norgate Platinum occupancies and bounded bars.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Cached fja05680 CSV (read-only; default data/raw/sp500_historical.csv).",
    )
    parser.add_argument(
        "--skip-bars",
        action="store_true",
        help="Write the occupancy map only; do not export price series.",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="Optional cap on mapped occupancies to export bars for (0 = all mapped).",
    )
    return parser.parse_args()


def _write_conflicts(path: Path, mappings: list[OccupancyMapping]) -> None:
    conflicts = [row for row in mappings if row.mapping_status == "CONFLICT"]
    write_csv(
        path,
        OCCUPANCY_CSV_FIELDS,
        [row.as_csv_dict() for row in conflicts],
    )


def _write_suffix_discovery(
    path: Path,
    suffixes: dict[str, str],
    discovered: dict[str, list[str]],
) -> None:
    rows: list[dict[str, str]] = []
    tickers = sorted(set(suffixes) | set(discovered))
    for ticker in tickers:
        if ":" in ticker:
            continue
        frozen = suffixes.get(ticker, "")
        actual = ",".join(discovered.get(ticker, []))
        rows.append(
            {
                "ticker": ticker,
                "frozen_suffix": frozen,
                "discovered_suffixes": actual,
                "frozen_in_discovered": "true" if frozen and frozen in discovered.get(ticker, []) else "false",
            }
        )
    write_csv(
        path,
        ("ticker", "frozen_suffix", "discovered_suffixes", "frozen_in_discovered"),
        rows,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        layout = ensure_layout(trial_layout(args.output_dir))
    except IsolationError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        loaded = SP500HistoricalSource().load(source_file=args.source_file)
    except UniverseSourceError as exc:
        raise SystemExit(str(exc)) from exc

    master = load_known_identities_catalog()
    occupancies = build_occupancies(list(loaded.memberships), master)
    LOGGER.info("Built %s occupancies from PIT + overlays.", len(occupancies))

    module, import_error = import_norgatedata()
    if module is None:
        raise SystemExit(import_error or "norgatedata is not importable.")
    running, databases, errors = norgate_status(module)
    if not running:
        raise SystemExit("NDU is not running; " + "; ".join(errors))
    delisted_present = any(name.casefold() == "us equities delisted" for name in databases)
    delisted_symbols = load_delisted_symbols(module) if delisted_present else []
    suffix_map = frozen_suffix_map(list(FROZEN_SAMPLE))
    discovered: dict[str, list[str]] = {}

    mappings: list[OccupancyMapping] = []
    for occupancy in occupancies:
        ticker = occupancy.pit_ticker
        if ticker not in discovered:
            discovered[ticker] = discover_delisted_suffixes(ticker, delisted_symbols)
        frozen = suffix_map.get(ticker, "")
        if occupancy.occupancy_end is not None:
            frozen = suffix_map.get(f"{ticker}:{occupancy.occupancy_end.isoformat()}", frozen)
        mapping = map_occupancy(
            occupancy,
            module,
            master=master,
            frozen_suffix=frozen,
            discovered_suffixes=discovered[ticker],
            successor_symbol=successor_for(ticker),
        )
        mappings.append(mapping)

    write_csv(layout.occupancy, OCCUPANCY_CSV_FIELDS, [row.as_csv_dict() for row in mappings])
    _write_conflicts(layout.conflicts, mappings)
    _write_suffix_discovery(layout.suffix_discovery, suffix_map, discovered)
    LOGGER.info("Wrote occupancy map %s", layout.occupancy)

    if args.skip_bars:
        return 0

    exported = 0
    seen_assetids: set[str] = set()
    for mapping in mappings:
        if mapping.mapping_status != "MAPPED" or not mapping.norgate_asset_id:
            continue
        if mapping.norgate_asset_id in seen_assetids:
            continue
        if args.max_symbols and exported >= args.max_symbols:
            break
        symbol = mapping.norgate_symbol or mapping.occupancy.pit_ticker
        totalreturn = bars_from_timeseries(
            symbol,
            price_timeseries(module, symbol, "TOTALRETURN"),
            adjusted=True,
        )
        unadjusted = bars_from_timeseries(
            symbol,
            price_timeseries(module, symbol, "NONE"),
            adjusted=False,
        )
        totalreturn = clip_to_occupancy(totalreturn, mapping.occupancy)
        unadjusted = clip_to_occupancy(unadjusted, mapping.occupancy)
        write_bar_csv(layout.totalreturn_dir / f"{mapping.norgate_asset_id}.csv", totalreturn)
        write_bar_csv(layout.unadjusted_dir / f"{mapping.norgate_asset_id}.csv", unadjusted)
        seen_assetids.add(mapping.norgate_asset_id)
        exported += 1
    LOGGER.info("Exported bars for %s assetids.", exported)
    return 0


if __name__ == "__main__":
    sys.exit(main())
