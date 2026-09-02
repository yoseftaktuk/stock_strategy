from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.backtest.diagnostics import (
    CURRENT_UNIVERSE_WARNING,
    DataCoverageSnapshot,
    RebalanceDiagnostics,
    format_rebalance_diagnostics,
    is_current_universe,
    universe_display_name,
)
from app.domain.enums import OrderStatus
from app.domain.models.equity import EquityPoint
from app.domain.models.fill import Fill
from app.domain.models.order import Order


@dataclass(frozen=True)
class BacktestResult:
    start_date: date
    end_date: date
    initial_capital: Decimal
    final_equity: Decimal
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    number_of_trades: int
    winning_trades: int
    losing_trades: int
    total_commission: Decimal
    total_slippage: Decimal
    equity_curve: tuple[EquityPoint, ...] = field(default_factory=tuple)
    fills: tuple[Fill, ...] = field(default_factory=tuple)
    orders: tuple[Order, ...] = field(default_factory=tuple)
    spy_buy_hold_return: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    priced_symbols: tuple[str, ...] = field(default_factory=tuple)
    universe_member_peak: int | None = None
    missing_price_count: int = 0
    universe_kind: str | None = None
    rebalance_diagnostics: tuple[RebalanceDiagnostics, ...] = field(default_factory=tuple)
    coverage: DataCoverageSnapshot | None = None
    unusable_symbols: tuple[str, ...] = field(default_factory=tuple)
    unvalued_symbols: tuple[str, ...] = field(default_factory=tuple)

    @property
    def universe_label(self) -> str:
        return universe_display_name(self.universe_kind)

    def format_report(self, *, verbose: bool = False) -> str:
        spy_line = ""
        if self.spy_buy_hold_return is not None:
            spy_line = f"\nSPY Buy & Hold:\n{self.spy_buy_hold_return * 100:.2f}%"
        warning_block = ""
        snapshot = self.coverage
        report_warnings = [
            warning for warning in self.warnings
            if warning != CURRENT_UNIVERSE_WARNING
            and warning != (snapshot.warning if snapshot is not None else None)
        ]
        if report_warnings:
            warning_block = "\nWarnings:\n" + "\n".join(report_warnings)
        coverage_block = ""
        if snapshot is not None:
            coverage_block = (
                f"\nPIT universe (peak):\n{snapshot.universe_member_peak}"
                f"\nUnique constituents:\n{snapshot.universe_members}"
                f"\nMarket Data Available:\n{snapshot.market_data_available}"
                f"\nMissing Market Data:\n{snapshot.missing_market_data}"
                f"\nUnusable Market Data:\n{snapshot.unusable_market_data}"
                f"\nInsufficient History:\n{snapshot.insufficient_history}"
                f"\nMomentum Eligible:\n{snapshot.momentum_eligible}"
                f"\nSelected:\n{snapshot.selected}"
            )
            if snapshot.warning:
                coverage_block += f"\n{snapshot.warning}"
        elif self.priced_symbols or self.universe_member_peak is not None:
            priced = ", ".join(self.priced_symbols) if self.priced_symbols else "none"
            coverage_block = f"\nSymbols with prices:\n{priced}"
            if self.universe_member_peak is not None:
                coverage_block += (
                    f"\nPIT universe (peak):\n{self.universe_member_peak}"
                    f"\nMissing prices:\n{self.missing_price_count}"
                )
        universe_block = f"\nUniverse:\n{self.universe_label}"
        if is_current_universe(self.universe_kind):
            universe_block += f"\n{CURRENT_UNIVERSE_WARNING}"
        diagnostics_block = ""
        if verbose:
            formatted = format_rebalance_diagnostics(self.rebalance_diagnostics)
            if formatted:
                diagnostics_block = f"\n{formatted}"
        return (
            "========================================\n"
            "BACKTEST RESULT\n"
            "========================================\n"
            "Period:\n"
            f"{self.start_date.isoformat()} → {self.end_date.isoformat()}"
            f"{universe_block}\n"
            "Initial Capital:\n"
            f"${self.initial_capital:,.2f}\n"
            "Final Equity:\n"
            f"${self.final_equity:,.2f}\n"
            "Total Return:\n"
            f"{self.total_return * 100:.2f}%\n"
            "CAGR:\n"
            f"{self.annualized_return * 100:.2f}%\n"
            "Volatility:\n"
            f"{self.volatility * 100:.2f}%\n"
            "Sharpe:\n"
            f"{self.sharpe_ratio:.2f}\n"
            "Max Drawdown:\n"
            f"{self.max_drawdown * 100:.2f}%\n"
            "Fills:\n"
            f"{self.number_of_trades}\n"
            "Commission:\n"
            f"${self.total_commission:,.2f}\n"
            "Slippage:\n"
            f"${self.total_slippage:,.2f}"
            f"{spy_line}"
            f"{coverage_block}"
            f"{warning_block}"
            f"{diagnostics_block}\n"
            "========================================"
        )

    def format_data_quality_report(self) -> str:
        snapshot = self.coverage
        rejected = sum(1 for order in self.orders if order.status == OrderStatus.REJECTED)
        unusable_fills = sorted({fill.symbol for fill in self.fills if fill.symbol in set(self.unusable_symbols)})
        stale_mtm = self._stale_mtm_after_series_end()
        stuck = tuple(self.unvalued_symbols)
        if stuck or unusable_fills or stale_mtm:
            status = "DATA_QUALITY_INCOMPLETE"
        elif (snapshot is not None and snapshot.missing_market_data > 0) or self.unusable_symbols:
            status = "DATA_QUALITY_INCOMPLETE"
        else:
            status = "COMPLETE"
        peak = snapshot.universe_member_peak if snapshot is not None else self.universe_member_peak
        members = snapshot.universe_members if snapshot is not None else 0
        missing = snapshot.missing_market_data if snapshot is not None else self.missing_price_count
        unusable_count = snapshot.unusable_market_data if snapshot is not None else len(self.unusable_symbols)
        unusable_list = ", ".join(self.unusable_symbols) if self.unusable_symbols else "none"
        stuck_list = ", ".join(stuck) if stuck else "none"
        fill_list = ", ".join(unusable_fills) if unusable_fills else "none"
        warning_text = "\n".join(self.warnings) if self.warnings else "none"
        return (
            "DATA QUALITY VALIDATION\n"
            f"Period: {self.start_date.isoformat()} → {self.end_date.isoformat()}\n"
            f"Universe: {self.universe_label}\n"
            f"PIT members encountered: {members}\n"
            f"PIT universe peak: {peak}\n"
            f"Missing price data: {missing}\n"
            f"Unusable price series: {unusable_count}\n"
            f"Unusable symbols: {unusable_list}\n"
            f"Fills involving unusable symbols: {fill_list}\n"
            f"Orders: {len(self.orders)}\n"
            f"Fills: {self.number_of_trades}\n"
            f"Rejected orders: {rejected}\n"
            f"Stuck unvalued positions: {stuck_list}\n"
            f"Stale last-price MTM after series end: {'yes' if stale_mtm else 'no'}\n"
            f"Final status: {status}\n"
            "Research readiness: NOT READY\n"
            f"Warnings:\n{warning_text}\n"
        )

    def _stale_mtm_after_series_end(self) -> bool:
        if not self.unvalued_symbols:
            return False
        for warning in self.warnings:
            if "holding last price" not in warning:
                continue
            if any(f"symbol={symbol}" in warning for symbol in self.unvalued_symbols):
                return True
        return False
