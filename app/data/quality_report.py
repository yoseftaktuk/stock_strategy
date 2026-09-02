"""Reusable market-data quality inspection helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.models.market_bar import MarketBar


@dataclass(frozen=True)
class SymbolQualityStats:
    symbol: str
    bar_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    duplicate_count: int
    missing_adjusted_close_count: int
    non_positive_price_count: int
    non_positive_volume_count: int
    suspicious_gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketDataQualityReport:
    symbol_count: int
    total_bars: int
    bars_per_symbol: dict[str, int]
    earliest_timestamp: datetime | None
    latest_timestamp: datetime | None
    duplicate_count: int
    missing_adjusted_close_count: int
    non_positive_price_count: int
    non_positive_volume_count: int
    suspicious_gaps: tuple[str, ...]
    per_symbol: tuple[SymbolQualityStats, ...] = field(default_factory=tuple)

    def format(self) -> str:
        lines = [
            "Market Data Quality Report",
            f"Symbols: {self.symbol_count}",
            f"Total bars: {self.total_bars}",
            f"Earliest: {self.earliest_timestamp.isoformat() if self.earliest_timestamp else 'n/a'}",
            f"Latest: {self.latest_timestamp.isoformat() if self.latest_timestamp else 'n/a'}",
            f"Duplicates: {self.duplicate_count}",
            f"Missing adjusted_close: {self.missing_adjusted_close_count}",
            f"Non-positive prices: {self.non_positive_price_count}",
            f"Non-positive volume: {self.non_positive_volume_count}",
        ]
        for symbol, count in sorted(self.bars_per_symbol.items()):
            lines.append(f"  {symbol}: {count}")
        if self.suspicious_gaps:
            lines.append("Suspicious gaps:")
            lines.extend(f"  - {gap}" for gap in self.suspicious_gaps)
        return "\n".join(lines)


def inspect_market_bars(bars: Sequence[MarketBar]) -> MarketDataQualityReport:
    by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol.upper()].append(bar)

    per_symbol: list[SymbolQualityStats] = []
    total_duplicates = 0
    total_missing_adj = 0
    total_bad_prices = 0
    total_bad_volume = 0
    all_gaps: list[str] = []
    earliest: datetime | None = None
    latest: datetime | None = None
    bars_per_symbol: dict[str, int] = {}

    for symbol, symbol_bars in sorted(by_symbol.items()):
        ordered = sorted(symbol_bars, key=lambda item: item.timestamp)
        seen: set[datetime] = set()
        duplicates = 0
        missing_adj = 0
        bad_prices = 0
        bad_volume = 0
        gaps: list[str] = []

        for bar in ordered:
            if bar.timestamp in seen:
                duplicates += 1
            seen.add(bar.timestamp)
            if bar.adjusted_close is None:
                missing_adj += 1
            prices = [bar.open, bar.high, bar.low, bar.close]
            if bar.adjusted_close is not None:
                prices.append(bar.adjusted_close)
            if any(price <= 0 for price in prices):
                bad_prices += 1
            if bar.volume <= 0:
                bad_volume += 1

        for previous, current in zip(ordered, ordered[1:], strict=False):
            delta = current.timestamp.date() - previous.timestamp.date()
            if delta > timedelta(days=5) and _looks_like_weekday_gap(previous, current):
                gap = (
                    f"{symbol}: {previous.timestamp.date().isoformat()} -> "
                    f"{current.timestamp.date().isoformat()} ({delta.days} days)"
                )
                gaps.append(gap)

        first_ts = ordered[0].timestamp if ordered else None
        last_ts = ordered[-1].timestamp if ordered else None
        if first_ts is not None and (earliest is None or first_ts < earliest):
            earliest = first_ts
        if last_ts is not None and (latest is None or last_ts > latest):
            latest = last_ts

        bars_per_symbol[symbol] = len(ordered)
        total_duplicates += duplicates
        total_missing_adj += missing_adj
        total_bad_prices += bad_prices
        total_bad_volume += bad_volume
        all_gaps.extend(gaps)
        per_symbol.append(
            SymbolQualityStats(
                symbol=symbol,
                bar_count=len(ordered),
                first_timestamp=first_ts,
                last_timestamp=last_ts,
                duplicate_count=duplicates,
                missing_adjusted_close_count=missing_adj,
                non_positive_price_count=bad_prices,
                non_positive_volume_count=bad_volume,
                suspicious_gaps=tuple(gaps),
            )
        )

    return MarketDataQualityReport(
        symbol_count=len(by_symbol),
        total_bars=len(bars),
        bars_per_symbol=bars_per_symbol,
        earliest_timestamp=earliest,
        latest_timestamp=latest,
        duplicate_count=total_duplicates,
        missing_adjusted_close_count=total_missing_adj,
        non_positive_price_count=total_bad_prices,
        non_positive_volume_count=total_bad_volume,
        suspicious_gaps=tuple(all_gaps),
        per_symbol=tuple(per_symbol),
    )


def _looks_like_weekday_gap(previous: MarketBar, current: MarketBar) -> bool:
    """Flag only gaps that span more than a normal long weekend/holiday cluster."""
    return (current.timestamp.date() - previous.timestamp.date()).days > 5
