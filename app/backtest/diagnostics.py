"""Per-rebalance universe and filter diagnostics for backtest reports."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.universe.factory import CURRENT, HISTORICAL_SP500

EXPLICIT_UNIVERSE = "explicit"
CURRENT_UNIVERSE_WARNING = (
    "CURRENT UNIVERSE WARNING: SURVIVORSHIP-BIASED FOR HISTORICAL BACKTESTING"
)


@dataclass(frozen=True)
class DataCoverageSnapshot:
    """Aggregate market-data coverage for a backtest run.

    Computed by the engine. Streamlit must display these values, not recompute them.
    """

    universe_member_peak: int | None = None
    universe_members: int = 0
    market_data_available: int = 0
    missing_market_data: int = 0
    insufficient_history: int = 0
    momentum_eligible: int = 0
    selected: int = 0
    warning: str | None = None


@dataclass(frozen=True)
class RebalanceDiagnostics:
    as_of: date
    universe_members: int
    missing_market_data: int
    insufficient_history: int
    failed_price_filter: int
    failed_liquidity_filter: int
    momentum_eligible: int
    selected: int

    def format_block(self) -> str:
        return (
            f"Rebalance: {self.as_of.isoformat()}\n"
            f"Universe Members: {self.universe_members}\n"
            f"Missing Market Data: {self.missing_market_data}\n"
            f"Insufficient History: {self.insufficient_history}\n"
            f"Failed Price Filter: {self.failed_price_filter}\n"
            f"Failed Liquidity Filter: {self.failed_liquidity_filter}\n"
            f"Momentum Eligible: {self.momentum_eligible}\n"
            f"Selected: {self.selected}"
        )


def universe_display_name(kind: str | None) -> str:
    if kind == HISTORICAL_SP500:
        return "Historical S&P 500 Point-in-Time"
    if kind == CURRENT:
        return "current"
    return EXPLICIT_UNIVERSE


def is_current_universe(kind: str | None) -> bool:
    return kind == CURRENT


def format_rebalance_diagnostics(rows: Sequence[RebalanceDiagnostics]) -> str:
    if not rows:
        return ""
    return "\n\n".join(row.format_block() for row in rows)


def historical_market_data_coverage_warning(missing_market_data: int) -> str | None:
    """Warning when PIT membership is applied but local prices are incomplete."""
    if missing_market_data <= 0:
        return None
    return (
        "Historical S&P 500 membership is applied.\n\n"
        "Market data is currently incomplete:\n"
        f"{missing_market_data} historical constituents have no local price data.\n\n"
        "The current result is NOT a full S&P 500 historical backtest."
    )
