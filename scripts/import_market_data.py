#!/usr/bin/env python3
"""Import historical market data from the configured provider into PostgreSQL."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from app.application.market_data_import import (
    DEFAULT_REQUEST_DELAY_SECONDS,
    fetch_start_for_import,
    import_market_data_batch,
    import_one_with_service,
    resolve_import_symbols,
)
from app.config.settings import Settings
from app.data.exceptions import DataImportError
from app.data.factory import create_market_data_provider
from app.data.market_data import MarketDataService
from app.data.quality_report import inspect_market_bars
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.market_data import PostgresMarketDataRepository
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.universe.factory import HISTORICAL_SP500
from app.universe.service import UniverseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import historical market data into PostgreSQL.")
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        required=False,
        help="Symbol to import. Repeat to import multiple symbols.",
    )
    parser.add_argument(
        "--universe",
        choices=(HISTORICAL_SP500,),
        default=None,
        help="Import every historical PIT constituent overlapping [start, end].",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--provider",
        choices=("csv", "historical"),
        default=None,
        help="Data provider override (default: DATA_PROVIDER from settings).",
    )
    args = parser.parse_args()
    if not args.symbols and not args.universe:
        parser.error("either --symbol or --universe historical_sp500 is required")
    return args


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    settings = Settings()
    try:
        ensure_database_available(settings)
    except DatabaseConnectionError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    provider = create_market_data_provider(settings, provider_name=args.provider)
    try:
        with session_scope(settings) as session:
            universe_service = UniverseService(PostgresSP500ConstituentRepository(session))
            symbols, universe = resolve_import_symbols(
                symbols=args.symbols,
                universe=args.universe,
                start=args.start,
                end=args.end,
                universe_service=universe_service,
            )
    except DataImportError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    fetch_start = fetch_start_for_import(
        args.start,
        universe=universe,
        lookback_days=settings.momentum_lookback,
    )
    strict_range_coverage = universe != HISTORICAL_SP500
    delay = DEFAULT_REQUEST_DELAY_SECONDS if (args.provider or settings.data_provider).upper() == "HISTORICAL" else 0.0
    all_bars = []
    collect_quality = universe != HISTORICAL_SP500

    def _import_symbol(symbol: str):
        with session_scope(settings) as session:
            repository = PostgresMarketDataRepository(
                session,
                batch_size=settings.market_data_insert_batch_size,
            )
            service = MarketDataService(provider=provider, repository=repository)
            summary = import_one_with_service(
                service,
                symbol,
                fetch_start,
                args.end,
                strict_range_coverage=strict_range_coverage,
            )
            print(summary)
            print()
            if collect_quality:
                all_bars.extend(list(service.get_history(symbol, fetch_start, args.end)))
            return summary

    report = import_market_data_batch(
        symbols,
        args.start,
        args.end,
        universe=universe,
        warmup_start=fetch_start,
        import_symbol=_import_symbol,
        request_delay_seconds=delay,
    )
    print(report.format())
    print()

    if all_bars:
        quality = inspect_market_bars(all_bars)
        print(quality.format())
        print()

    if report.failed:
        raise SystemExit(1)

    print("Overall status: SUCCESS")


if __name__ == "__main__":
    main()
