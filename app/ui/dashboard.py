from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.backtest.diagnostics import CURRENT_UNIVERSE_WARNING, is_current_universe
from app.backtest.exceptions import EmptyUniverseError, InsufficientHistoryError
from app.backtest.result import BacktestResult
from app.backtest.runner import available_symbols, run_momentum_backtest
from app.backtest.export import equity_csv_text, fills_csv_text, orders_csv_text
from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.ui.presentation import (
    coverage_table,
    equity_table,
    fills_table,
    rebalance_diagnostics_table,
    summary_table,
)
from app.universe.exceptions import UniverseProviderError
from app.universe.factory import CURRENT, HISTORICAL_SP500

DEFAULT_START = date(2015, 1, 1)
DEFAULT_END = date(2025, 12, 31)
DEFAULT_CAPITAL = 100_000.0
UNIVERSE_IMPORTED = "Imported price files"
UNIVERSE_OPTIONS = {
    UNIVERSE_IMPORTED: None,
    "Historical S&P 500 (point-in-time)": HISTORICAL_SP500,
    "Current S&P 500 (survivorship-biased)": CURRENT,
}


def main() -> None:
    st.set_page_config(page_title="Momentum Backtest", layout="wide")
    st.title("Momentum Backtest")
    st.caption("Run the 12-1 momentum strategy on imported daily history.")

    settings = Settings()
    symbols = available_symbols(settings)

    with st.sidebar:
        st.header("Parameters")
        start = st.date_input("Start date", value=DEFAULT_START)
        end = st.date_input("End date", value=DEFAULT_END)
        capital = st.number_input(
            "Initial capital (USD)",
            min_value=1.0,
            value=DEFAULT_CAPITAL,
            step=1000.0,
            format="%.2f",
        )
        universe_label = st.selectbox(
            "Universe",
            options=list(UNIVERSE_OPTIONS),
            index=0,
            help=(
                "Imported price files uses locally imported CSVs. "
                "Historical S&P 500 uses point-in-time constituents from PostgreSQL. "
                "Coverage (members vs local prices) is reported after the run."
            ),
        )
        selected: list[str] = []
        if universe_label == UNIVERSE_IMPORTED:
            selected = st.multiselect(
                "Symbols",
                options=list(symbols),
                default=list(symbols),
            )
        run_clicked = st.button("Run backtest", type="primary")

    if not isinstance(start, date) or not isinstance(end, date):
        st.error("Start and end must be calendar dates.")
        return
    if start > end:
        st.error("Start date must be on or before end date.")
        return

    if run_clicked:
        _run_and_store(
            start,
            end,
            Decimal(str(capital)),
            selected,
            universe=UNIVERSE_OPTIONS[universe_label],
        )

    result = st.session_state.get("backtest_result")
    error = st.session_state.get("backtest_error")
    if error:
        st.error(error)
    if result is None:
        if not error:
            st.info("Choose dates, capital, and symbols, then run the backtest.")
        return
    _render_result(result)


def _run_and_store(
    start: date,
    end: date,
    capital: Decimal,
    selected: list[str],
    universe: str | None = None,
) -> None:
    st.session_state.pop("backtest_result", None)
    st.session_state.pop("backtest_error", None)
    try:
        with st.spinner("Running backtest..."):
            result = run_momentum_backtest(
                start,
                end,
                capital=capital,
                symbols=selected or None,
                universe=universe,
            )
    except (EmptyUniverseError, InsufficientHistoryError, DatabaseConnectionError, UniverseProviderError) as exc:
        st.session_state["backtest_error"] = str(exc)
        return
    st.session_state["backtest_result"] = result


def _render_result(result: BacktestResult) -> None:
    if is_current_universe(result.universe_kind):
        st.warning(CURRENT_UNIVERSE_WARNING)
    coverage_warning = result.coverage.warning if result.coverage is not None else None
    if coverage_warning:
        st.warning(coverage_warning)
    quality_warnings = [
        warning
        for warning in result.warnings
        if "Unusable price series" in warning
        or "Price-quality validation failed" in warning
        or "position left unvalued" in warning
    ]
    for warning in quality_warnings:
        st.warning(warning)
    other_warnings = [
        warning
        for warning in result.warnings
        if warning != CURRENT_UNIVERSE_WARNING
        and warning != coverage_warning
        and warning not in quality_warnings
    ]
    if other_warnings:
        with st.expander(f"Warnings ({len(other_warnings)})", expanded=True):
            for warning in other_warnings:
                st.warning(warning)

    summary = summary_table(result)
    coverage = coverage_table(result)
    equity = equity_table(result)
    fills = fills_table(result)
    diagnostics = rebalance_diagnostics_table(result)

    st.subheader("Results")
    st.dataframe(summary, hide_index=True, width="stretch")

    if not coverage.empty:
        st.subheader("Data coverage")
        st.dataframe(coverage, hide_index=True, width="stretch")

    if not diagnostics.empty:
        with st.expander(f"Rebalance diagnostics ({len(diagnostics)})", expanded=False):
            st.dataframe(diagnostics, hide_index=True, width="stretch")

    if equity.empty:
        st.info("No equity curve points for this run.")
    else:
        left, right = st.columns(2)
        with left:
            st.subheader("Equity")
            st.plotly_chart(_equity_figure(equity), width="stretch")
        with right:
            st.subheader("Drawdown")
            st.plotly_chart(_drawdown_figure(equity), width="stretch")

    st.subheader("Fills")
    st.caption(
        "Fills are successful executions from BacktestResult "
        "(number_of_trades = fill count; one fill per accepted order). "
        "Side comes from the related Order. Winning / Losing counts SELL fills versus average cost only."
    )
    if fills.empty:
        st.info("No fills.")
    else:
        st.dataframe(fills, hide_index=True, width="stretch")

    left_dl, mid_dl, right_dl = st.columns(3)
    with left_dl:
        st.download_button(
            "Download fills.csv",
            data=fills_csv_text(result),
            file_name="fills.csv",
            mime="text/csv",
            key="download_fills",
        )
    with mid_dl:
        st.download_button(
            "Download orders.csv",
            data=orders_csv_text(result),
            file_name="orders.csv",
            mime="text/csv",
            key="download_orders",
        )
    with right_dl:
        st.download_button(
            "Download equity_curve.csv",
            data=equity_csv_text(result),
            file_name="equity_curve.csv",
            mime="text/csv",
            key="download_equity",
        )


def _equity_figure(equity: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["Equity"],
            name="Equity",
            line={"color": "#1f77b4", "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["Cash"],
            name="Cash",
            yaxis="y2",
            line={"color": "#7f7f7f", "width": 1, "dash": "dot"},
        )
    )
    fig.update_layout(
        margin={"l": 40, "r": 40, "t": 20, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        yaxis={"title": "Equity (USD)", "tickprefix": "$"},
        yaxis2={"title": "Cash (USD)", "overlaying": "y", "side": "right", "showgrid": False},
        hovermode="x unified",
    )
    return fig


def _drawdown_figure(equity: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity["Date"],
            y=equity["Drawdown %"],
            name="Drawdown",
            fill="tozeroy",
            line={"color": "#d62728", "width": 1.5},
        )
    )
    fig.update_layout(
        margin={"l": 40, "r": 40, "t": 20, "b": 40},
        yaxis={"title": "Drawdown", "ticksuffix": "%"},
        hovermode="x unified",
        showlegend=False,
    )
    return fig


main()
