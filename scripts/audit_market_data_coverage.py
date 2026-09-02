#!/usr/bin/env python3
"""Audit PIT membership versus local market-data coverage and identity.

Loads memberships from the cached CSV by default (no network). Does not
download market data and does not delete memberships.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from app.data.pit_coverage import (
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    build_pit_coverage,
    write_coverage_artifacts,
)
from app.security_master.seed import load_known_identities_catalog
from app.universe.audit import load_price_windows_from_csv
from app.universe.exceptions import UniverseSourceError
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit historical S&P 500 PIT market-data coverage and identity."
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Cached fja05680 CSV (default: data/raw/sp500_historical.csv). No network.",
    )
    parser.add_argument(
        "--price-path",
        type=Path,
        default=Path("data/raw"),
        help="Local OHLCV CSV directory used for first/last bar dates.",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_WINDOW_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_WINDOW_END)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("audit/market_data_coverage"),
        help="Directory for coverage.csv, coverage.json, and missing.csv.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    path = Path(args.source_file)
    try:
        loaded = SP500HistoricalSource().load(source_file=path)
    except UniverseSourceError as exc:
        raise SystemExit(str(exc)) from exc
    price_windows = load_price_windows_from_csv(args.price_path)
    master = load_known_identities_catalog()
    report = build_pit_coverage(
        loaded.memberships,
        price_windows,
        master,
        start=args.start,
        end=args.end,
        universe_source=str(path),
    )
    write_coverage_artifacts(report, args.output_dir)
    print(report.format())
    print()
    print(f"Wrote {args.output_dir / 'coverage.csv'}")
    print(f"Wrote {args.output_dir / 'coverage.json'}")
    print(f"Wrote {args.output_dir / 'missing.csv'}")
    missing = report.missing_rows()
    if missing:
        print()
        print("Missing listing CSV (sample of 20):")
        for row in missing[:20]:
            print(
                f"- {row.historical_ticker}: reason={row.reason or 'n/a'} "
                f"identity={row.identity_status} vendor={row.vendor_symbol} "
                f"rebalance={row.rebalance_encountered}"
            )


if __name__ == "__main__":
    main()
