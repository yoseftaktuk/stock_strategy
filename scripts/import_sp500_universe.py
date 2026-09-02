#!/usr/bin/env python3
"""Import historical S&P 500 constituent membership into PostgreSQL.

Downloads the public fja05680/sp500 dataset unless --source-file is provided.
Does not download market data. Re-running the import is idempotent.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.universe.exceptions import UniverseSourceError, UniverseValidationError
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource
from app.universe.service import UniverseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import historical S&P 500 constituents into PostgreSQL.")
    parser.add_argument(
        "--source-file",
        type=Path,
        default=None,
        help="Local CSV path (skips network download).",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="Override the public GitHub raw CSV URL.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Where to cache a downloaded CSV.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    settings = Settings()
    try:
        ensure_database_available(settings)
    except DatabaseConnectionError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    source = SP500HistoricalSource(cache_path=args.cache_path)
    try:
        loaded = source.load(source_file=args.source_file, source_url=args.source_url)
    except UniverseSourceError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    try:
        with session_scope(settings) as session:
            repository = PostgresSP500ConstituentRepository(session)
            service = UniverseService(repository)
            summary = service.persist_memberships(
                loaded.memberships,
                source=loaded.source,
                source_version=loaded.source_version,
                raw_records=loaded.raw_records,
            )
    except UniverseValidationError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    print(summary.format())
    if loaded.cache_path is not None:
        print(f"Cache: {loaded.cache_path}")


if __name__ == "__main__":
    main()
