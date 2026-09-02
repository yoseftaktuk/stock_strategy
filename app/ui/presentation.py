from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.backtest.diagnostics import CURRENT_UNIVERSE_WARNING, is_current_universe
from app.backtest.result import BacktestResult


def summary_table(result: BacktestResult) -> pd.DataFrame:
    rows: list[dict[str, str]] = [
        {"Metric": "Period", "Value": f"{result.start_date.isoformat()} → {result.end_date.isoformat()}"},
        {"Metric": "Universe", "Value": result.universe_label},
        {"Metric": "Initial Capital", "Value": _money(result.initial_capital)},
        {"Metric": "Final Equity", "Value": _money(result.final_equity)},
        {"Metric": "Total Return", "Value": _pct(result.total_return)},
        {"Metric": "CAGR", "Value": _pct(result.annualized_return)},
        {"Metric": "Volatility", "Value": _pct(result.volatility)},
        {"Metric": "Sharpe", "Value": f"{result.sharpe_ratio:.2f}"},
        {"Metric": "Max Drawdown", "Value": _pct(result.max_drawdown)},
        {"Metric": "Fills", "Value": str(result.number_of_trades)},
        {
            "Metric": "Winning / Losing sells",
            "Value": f"{result.winning_trades} / {result.losing_trades}",
        },
        {"Metric": "Commission", "Value": _money(result.total_commission)},
        {"Metric": "Slippage", "Value": _money(result.total_slippage)},
    ]
    if is_current_universe(result.universe_kind):
        rows.append({"Metric": "Universe warning", "Value": CURRENT_UNIVERSE_WARNING})
    snapshot = result.coverage
    if snapshot is not None:
        if snapshot.universe_member_peak is not None:
            rows.append({"Metric": "PIT Universe Members", "Value": str(snapshot.universe_member_peak)})
        if snapshot.universe_members and snapshot.universe_members != snapshot.universe_member_peak:
            rows.append({"Metric": "Unique constituents", "Value": str(snapshot.universe_members)})
        rows.append({"Metric": "Market Data Available", "Value": str(snapshot.market_data_available)})
        rows.append({"Metric": "Missing Market Data", "Value": str(snapshot.missing_market_data)})
        rows.append({"Metric": "Unusable Market Data", "Value": str(snapshot.unusable_market_data)})
        rows.append({"Metric": "Insufficient History", "Value": str(snapshot.insufficient_history)})
        rows.append({"Metric": "Momentum Eligible", "Value": str(snapshot.momentum_eligible)})
        rows.append({"Metric": "Selected", "Value": str(snapshot.selected)})
    else:
        if result.priced_symbols:
            priced = ", ".join(result.priced_symbols) if len(result.priced_symbols) <= 20 else str(len(result.priced_symbols))
            rows.append({"Metric": "Symbols with prices", "Value": priced})
        if result.universe_member_peak is not None:
            rows.append({"Metric": "PIT universe (peak)", "Value": str(result.universe_member_peak)})
            rows.append({"Metric": "Missing prices", "Value": str(result.missing_price_count)})
    if result.unusable_symbols:
        preview = ", ".join(result.unusable_symbols[:20])
        rows.append({"Metric": "Unusable symbols", "Value": preview})
    if result.unvalued_symbols:
        rows.append({"Metric": "Unvalued residual positions", "Value": ", ".join(result.unvalued_symbols)})
    if result.spy_buy_hold_return is not None:
        rows.append({"Metric": "SPY Buy & Hold", "Value": _pct(result.spy_buy_hold_return)})
    return pd.DataFrame(rows)


def equity_table(result: BacktestResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Date": point.date,
                "Equity": float(point.equity),
                "Cash": float(point.cash),
                "Drawdown %": float(point.drawdown) * 100,
                "Daily Return %": float(point.returns) * 100,
            }
            for point in result.equity_curve
        ]
    )


def fills_table(result: BacktestResult) -> pd.DataFrame:
    orders_by_id = {order.client_order_id: order for order in result.orders}
    return pd.DataFrame(
        [
            {
                "Time": fill.timestamp.isoformat(),
                "Symbol": fill.symbol,
                "Side": (
                    orders_by_id[fill.order_id].side.value
                    if fill.order_id in orders_by_id
                    else ""
                ),
                "Quantity": float(fill.quantity),
                "Market Price": float(fill.market_price) if fill.market_price is not None else None,
                "Fill Price": float(fill.price),
                "Commission": float(fill.commission),
                "Slippage": float(fill.slippage),
                "Order ID": fill.order_id,
            }
            for fill in result.fills
        ]
    )


def rebalance_diagnostics_table(result: BacktestResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rebalance": row.as_of.isoformat(),
                "Universe Members": row.universe_members,
                "Missing Market Data": row.missing_market_data,
                "Unusable Market Data": row.unusable_market_data,
                "Insufficient History": row.insufficient_history,
                "Failed Price Filter": row.failed_price_filter,
                "Failed Liquidity Filter": row.failed_liquidity_filter,
                "Momentum Eligible": row.momentum_eligible,
                "Selected": row.selected,
            }
            for row in result.rebalance_diagnostics
        ]
    )


def coverage_table(result: BacktestResult) -> pd.DataFrame:
    snapshot = result.coverage
    if snapshot is None:
        return pd.DataFrame()
    rows = [
        {"Metric": "Universe", "Value": result.universe_label},
        {"Metric": "PIT Universe Members", "Value": str(snapshot.universe_member_peak or snapshot.universe_members)},
    ]
    if snapshot.universe_members and snapshot.universe_members != snapshot.universe_member_peak:
        rows.append({"Metric": "Unique constituents", "Value": str(snapshot.universe_members)})
    rows.extend(
        [
            {"Metric": "Market Data Available", "Value": str(snapshot.market_data_available)},
            {"Metric": "Missing Market Data", "Value": str(snapshot.missing_market_data)},
            {"Metric": "Unusable Market Data", "Value": str(snapshot.unusable_market_data)},
            {"Metric": "Insufficient History", "Value": str(snapshot.insufficient_history)},
            {"Metric": "Momentum Eligible", "Value": str(snapshot.momentum_eligible)},
            {"Metric": "Selected", "Value": str(snapshot.selected)},
        ]
    )
    if result.unusable_symbols:
        rows.append({"Metric": "Unusable symbols", "Value": ", ".join(result.unusable_symbols[:20])})
    if result.unvalued_symbols:
        rows.append({"Metric": "Unvalued residual positions", "Value": ", ".join(result.unvalued_symbols)})
    return pd.DataFrame(rows)


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"
