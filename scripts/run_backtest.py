#!/usr/bin/env python3
"""Run a local backtest using historical data and SimulatedBroker."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.backtest.exceptions import EmptyUniverseError, InsufficientHistoryError
from app.backtest.export import write_backtest_export
from app.backtest.runner import run_momentum_backtest
from app.backtest.universe_audit import write_detail_csv, write_summary_csv
from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import session_scope
from app.universe.audit import audit_universe, load_price_windows_from_csv
from app.universe.exceptions import UniverseProviderError
from app.universe.factory import UNIVERSE_CHOICES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the momentum strategy backtest.")
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--capital",
        type=Decimal,
        default=Decimal("100000"),
        help="Initial capital in USD",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Universe symbol. Repeat for multiple. Defaults to Settings.universe or CSV files in CSV_DATA_PATH.",
    )
    parser.add_argument(
        "--universe",
        choices=UNIVERSE_CHOICES,
        default=None,
        help=(
            "Named universe from PostgreSQL. historical_sp500 is point-in-time; "
            "current uses today's members for all dates (survivorship-biased). "
            "Ignored when --symbol is passed."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-rebalance universe and filter diagnostics.",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Write fills.csv, orders.csv, and equity_curve.csv into this directory.",
    )
    parser.add_argument(
        "--universe-audit",
        action="store_true",
        help="Write audit/universe_summary.csv for this run's rebalance dates.",
    )
    parser.add_argument(
        "--universe-audit-detail",
        action="store_true",
        help="Also write audit/universe_by_rebalance.csv (can be large).",
    )
    parser.add_argument(
        "--universe-audit-changes-only",
        action="store_true",
        help="Detail CSV includes only joins and leaves versus the prior rebalance.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    try:
        result = run_momentum_backtest(
            args.start,
            args.end,
            capital=args.capital,
            symbols=args.symbols,
            universe=args.universe,
        )
    except (EmptyUniverseError, InsufficientHistoryError, DatabaseConnectionError, UniverseProviderError) as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc
    print(result.format_report(verbose=args.verbose))
    print()
    print(result.format_data_quality_report())
    if args.export_dir is not None:
        fills_path, orders_path, equity_path = write_backtest_export(args.export_dir, result)
        quality_path = args.export_dir / "data_quality.txt"
        quality_path.write_text(result.format_data_quality_report(), encoding="utf-8")
        print(f"Wrote {fills_path}")
        print(f"Wrote {orders_path}")
        print(f"Wrote {equity_path}")
        print(f"Wrote {quality_path}")
    if args.universe_audit or args.universe_audit_detail:
        _write_universe_audit(args, result)


def _write_universe_audit(args: argparse.Namespace, result: object) -> None:
    from app.backtest.result import BacktestResult

    assert isinstance(result, BacktestResult)
    settings = Settings()
    with session_scope(settings) as session:
        memberships = list(PostgresSP500ConstituentRepository(session).get_all_memberships())
    dates = [row.as_of for row in result.rebalance_diagnostics]
    price_windows = load_price_windows_from_csv(Path(settings.csv_data_path))
    report = audit_universe(
        memberships,
        rebalance_dates=dates,
        price_windows=price_windows,
    )
    audit_dir = Path("audit")
    write_summary_csv(audit_dir / "universe_summary.csv", report)
    print(f"Wrote {audit_dir / 'universe_summary.csv'}")
    if args.universe_audit_detail:
        write_detail_csv(
            audit_dir / "universe_by_rebalance.csv",
            report,
            changes_only=args.universe_audit_changes_only,
        )
        print(f"Wrote {audit_dir / 'universe_by_rebalance.csv'}")


if __name__ == "__main__":
    main()
