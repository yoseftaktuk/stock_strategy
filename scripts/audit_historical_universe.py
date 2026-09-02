#!/usr/bin/env python3
"""Audit the historical S&P 500 point-in-time universe.

Loads memberships from the cached CSV by default (no network). Use --from-db
when PostgreSQL already holds imported intervals. Does not download market data
and does not delete memberships.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from app.backtest.universe_audit import write_detail_csv, write_summary_csv
from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.universe.audit import (
    CLASS_LABELS,
    audit_universe,
    load_price_windows_from_csv,
)
from app.universe.exceptions import UniverseSourceError
from app.universe.models import ConstituentMembership
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit historical S&P 500 PIT memberships.")
    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Cached fja05680 CSV (default: data/raw/sp500_historical.csv). No network.",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Load memberships from PostgreSQL instead of the cached CSV.",
    )
    parser.add_argument(
        "--price-path",
        type=Path,
        default=Path("data/raw"),
        help="Local OHLCV CSV directory used for first/last bar dates.",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2015, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument(
        "--symbols",
        default="XYZ,TKO,SE,HAR",
        help="Comma-separated symbols to investigate in addition to auto-flagged names.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("audit"),
        help="Directory for universe_summary.csv (and optional detail CSV).",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Write universe_by_rebalance.csv (can be large).",
    )
    parser.add_argument(
        "--changes-only",
        action="store_true",
        help="Detail CSV includes only joins and leaves versus the prior rebalance.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    memberships, origin = _load_memberships(args)
    price_windows = load_price_windows_from_csv(args.price_path)
    investigate = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]
    report = audit_universe(
        memberships,
        start=args.start,
        end=args.end,
        price_windows=price_windows,
        investigate_symbols=investigate,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_summary_csv(args.output_dir / "universe_summary.csv", report)
    if args.detail:
        write_detail_csv(
            args.output_dir / "universe_by_rebalance.csv",
            report,
            changes_only=args.changes_only,
        )
    print(_format_report(report, origin=origin, start=args.start, end=args.end))


def _load_memberships(args: argparse.Namespace) -> tuple[tuple[ConstituentMembership, ...], str]:
    if args.from_db:
        settings = Settings()
        try:
            ensure_database_available(settings)
        except DatabaseConnectionError as exc:
            raise SystemExit(str(exc)) from exc
        with session_scope(settings) as session:
            rows = tuple(PostgresSP500ConstituentRepository(session).get_all_memberships())
        if not rows:
            raise SystemExit("PostgreSQL has no S&P 500 memberships. Import the universe first.")
        return rows, "postgresql"

    path = Path(args.source_file)
    try:
        loaded = SP500HistoricalSource().load(source_file=path)
    except UniverseSourceError as exc:
        raise SystemExit(str(exc)) from exc
    return loaded.memberships, str(path)


def _format_report(report: object, *, origin: str, start: date, end: date) -> str:
    from app.universe.audit import UniverseAuditReport

    assert isinstance(report, UniverseAuditReport)
    lines = [
        "Historical S&P 500 PIT universe audit",
        f"Source: {origin}",
        f"Window: {start.isoformat()} → {end.isoformat()}",
        f"Membership intervals: {len(report.memberships)}",
        f"Unique symbols: {len(report.unique_symbols)}",
        f"Rebalance dates: {len(report.rebalances)}",
        f"Duplicates: {report.duplicate_count}",
        f"Overlapping intervals: {report.overlapping_count}",
        f"Invalid intervals: {report.invalid_interval_count}",
        f"Fixture symbols: {len(report.fixture_symbols)}",
        f"Late price start: {len(report.late_price_start)}",
        f"Membership after prices: {len(report.membership_after_prices)}",
        f"Extreme first price: {len(report.extreme_first_price)}",
        f"Current-only leakage: {len(report.current_only_leakage)}",
        f"Suspicious symbols: {len(report.suspicious_symbols)}",
    ]
    if report.rebalances:
        sizes = [len(row.symbols) for row in report.rebalances]
        lines.append(f"Universe size min/max: {min(sizes)} / {max(sizes)}")
    if report.suspicious_symbols:
        preview = ", ".join(report.suspicious_symbols[:40])
        extra = "" if len(report.suspicious_symbols) <= 40 else f" (+{len(report.suspicious_symbols) - 40})"
        lines.append(f"Suspicious list: {preview}{extra}")
    lines.append("")
    lines.append("Investigations")
    for item in report.investigations:
        lines.append(
            f"- {item.symbol}: {item.classification} {CLASS_LABELS[item.classification]}"
        )
        intervals = "; ".join(
            f"{period.start_date.isoformat()}→"
            f"{period.end_date.isoformat() if period.end_date else 'open'}"
            for period in item.intervals
        )
        lines.append(f"    intervals: {intervals or 'none'}")
        lines.append(f"    source: {item.source or 'n/a'}")
        first = item.first_appearance.isoformat() if item.first_appearance else "n/a"
        last = item.last_appearance.isoformat() if item.last_appearance else "n/a"
        lines.append(f"    PIT appearance: {first} → {last} ({len(item.rebalance_dates)} rebalances)")
        price = (
            f"{item.price_first.isoformat()} → {item.price_last.isoformat()}"
            if item.price_first and item.price_last
            else "no local prices"
        )
        lines.append(f"    local prices: {price}")
        lines.append(f"    notes: {item.notes}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
