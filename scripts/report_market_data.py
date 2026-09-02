#!/usr/bin/env python3
"""Print a market-data coverage diagnostic from PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import date

from app.application.market_data_import import fetch_start_for_import, resolve_import_symbols
from app.config.settings import Settings
from app.data.coverage import build_market_data_coverage
from app.data.exceptions import DataImportError
from app.data.factory import create_market_data_provider
from app.data.market_data import MarketDataService
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.market_data import PostgresMarketDataRepository
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.universe.factory import HISTORICAL_SP500
from app.universe.service import UniverseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report market-data coverage from PostgreSQL.")
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        required=False,
        help="Symbol to inspect. Repeat for multiple symbols.",
    )
    parser.add_argument(
        "--universe",
        choices=(HISTORICAL_SP500,),
        default=None,
        help="Report coverage for historical PIT constituents overlapping [start, end].",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if not args.symbols and not args.universe:
        parser.error("either --symbol or --universe historical_sp500 is required")
    return args


def main() -> None:
    args = parse_args()
    settings = Settings()
    try:
        ensure_database_available(settings)
    except DatabaseConnectionError as exc:
        raise SystemExit(str(exc)) from exc

    create_market_data_provider(settings)

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
            warmup_start = fetch_start_for_import(
                args.start,
                universe=universe,
                lookback_days=settings.momentum_lookback,
            )
            repository = PostgresMarketDataRepository(session)
            service = MarketDataService(
                provider=create_market_data_provider(settings),
                repository=repository,
            )
            bars_by_symbol = {
                symbol: list(service.get_history(symbol, warmup_start, args.end)) for symbol in symbols
            }
            report = build_market_data_coverage(
                symbols,
                bars_by_symbol,
                start=warmup_start,
                end=args.end,
                lookback_days=settings.momentum_lookback,
                universe=universe,
                warmup_start=warmup_start,
            )
    except DataImportError as exc:
        raise SystemExit(str(exc)) from exc

    print(report.format())
    print()
    print(f"{'symbol':<10} {'bars':>8} {'first':>12} {'last':>12} {'status':<12}")
    for row in report.symbols:
        first = row.first_date.isoformat() if row.first_date else "n/a"
        last = row.last_date.isoformat() if row.last_date else "n/a"
        print(f"{row.symbol:<10} {row.row_count:>8} {first:>12} {last:>12} {row.download_status:<12}")


if __name__ == "__main__":
    main()
