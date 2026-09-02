#!/usr/bin/env python3
"""Report the persisted point-in-time S&P 500 universe."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.universe.models import ConstituentMembership
from app.universe.service import UniverseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report historical S&P 500 constituents as of a date.")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True, help="As-of date (YYYY-MM-DD)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    try:
        ensure_database_available(settings)
    except DatabaseConnectionError as exc:
        raise SystemExit(str(exc)) from exc

    with session_scope(settings) as session:
        repository = PostgresSP500ConstituentRepository(session)
        service = UniverseService(repository)
        symbols = service.get_symbols(args.as_of)
        memberships = list(repository.get_all_memberships())
        as_of_memberships = list(repository.get_memberships_as_of(args.as_of))

    print(_format_report(args.as_of, symbols, memberships, as_of_memberships))


def _format_report(
    as_of: date,
    symbols: list[str],
    memberships: list[ConstituentMembership],
    as_of_memberships: list[ConstituentMembership],
) -> str:
    by_symbol: dict[str, list[ConstituentMembership]] = defaultdict(list)
    for item in memberships:
        by_symbol[item.symbol].append(item)

    multi_period = sorted(symbol for symbol, periods in by_symbol.items() if len(periods) > 1)
    active = sorted(item.symbol for item in memberships if item.end_date is None)
    historical_only = sorted(
        symbol for symbol, periods in by_symbol.items() if all(item.end_date is not None for item in periods)
    )
    start_dates = [item.start_date for item in memberships]
    end_dates = [item.end_date for item in memberships if item.end_date is not None]
    earliest = min(start_dates).isoformat() if start_dates else "n/a"
    latest_start = max(start_dates).isoformat() if start_dates else "n/a"
    latest_end = max(end_dates).isoformat() if end_dates else "open"
    changes = sum(1 for item in memberships if item.end_date is not None) + len(active)

    first20 = ", ".join(symbols[:20]) if symbols else "(none)"
    last20 = ", ".join(symbols[-20:]) if len(symbols) > 20 else first20

    interval_lines = []
    for item in as_of_memberships[:20]:
        end = item.end_date.isoformat() if item.end_date is not None else "open"
        interval_lines.append(f"  {item.symbol:<8} {item.start_date.isoformat()} → {end}")
    if len(as_of_memberships) > 20:
        interval_lines.append(f"  ... {len(as_of_memberships) - 20} more")

    return "\n".join(
        [
            "Historical S&P 500 Universe Report",
            f"As-of date: {as_of.isoformat()}",
            f"Total members: {len(symbols)}",
            f"First 20 symbols: {first20}",
            f"Last 20 symbols: {last20}",
            f"Earliest membership date: {earliest}",
            f"Latest membership start: {latest_start}",
            f"Latest membership end: {latest_end}",
            f"Membership intervals (all-time): {len(memberships)}",
            f"Membership changes (closed + currently active): {changes}",
            f"Symbols with multiple membership periods: {len(multi_period)}",
            f"Currently active members: {len(active)}",
            f"Historical-only members: {len(historical_only)}",
            "Membership intervals as-of (first 20):",
            *interval_lines,
        ]
    )


if __name__ == "__main__":
    main()
