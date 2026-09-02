from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from dataclasses import replace

import pytest

from app.backtest.diagnostics import CURRENT_UNIVERSE_WARNING, DataCoverageSnapshot, RebalanceDiagnostics
from app.backtest.result import BacktestResult
from app.domain.models.equity import EquityPoint
from app.domain.models.fill import Fill
from app.ui.presentation import coverage_table, equity_table, fills_table, rebalance_diagnostics_table, summary_table
from app.universe.factory import CURRENT, HISTORICAL_SP500


def _result() -> BacktestResult:
    return BacktestResult(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),
        initial_capital=Decimal("100000"),
        final_equity=Decimal("105000.50"),
        total_return=0.05,
        annualized_return=0.12,
        volatility=0.2,
        sharpe_ratio=1.5,
        max_drawdown=-0.03,
        number_of_trades=2,
        winning_trades=1,
        losing_trades=1,
        total_commission=Decimal("10.25"),
        total_slippage=Decimal("5.00"),
        equity_curve=(
            EquityPoint(
                date=date(2024, 1, 2),
                equity=Decimal("100000"),
                cash=Decimal("100000"),
                returns=Decimal("0"),
                drawdown=Decimal("0"),
            ),
            EquityPoint(
                date=date(2024, 1, 3),
                equity=Decimal("105000.50"),
                cash=Decimal("20000"),
                returns=Decimal("0.05"),
                drawdown=Decimal("-0.01"),
            ),
        ),
        fills=(
            Fill(
                order_id="2024-01-03-0001",
                symbol="AAPL",
                quantity=Decimal("10"),
                price=Decimal("150.25"),
                commission=Decimal("1.50"),
                timestamp=datetime(2024, 1, 3, 14, 30, tzinfo=timezone.utc),
            ),
        ),
        spy_buy_hold_return=0.08,
        warnings=("example warning",),
    )


@pytest.mark.unit
def test_summary_table_formats_metrics() -> None:
    table = summary_table(_result())
    values = dict(zip(table["Metric"], table["Value"], strict=True))
    assert values["Period"] == "2024-01-02 → 2024-01-05"
    assert values["Universe"] == "explicit"
    assert values["Initial Capital"] == "$100,000.00"
    assert values["Final Equity"] == "$105,000.50"
    assert values["Total Return"] == "5.00%"
    assert values["CAGR"] == "12.00%"
    assert values["Volatility"] == "20.00%"
    assert values["Sharpe"] == "1.50"
    assert values["Max Drawdown"] == "-3.00%"
    assert values["Trades"] == "2"
    assert values["Winning / Losing"] == "1 / 1"
    assert values["Commission"] == "$10.25"
    assert values["Slippage"] == "$5.00"
    assert values["SPY Buy & Hold"] == "8.00%"


@pytest.mark.unit
def test_summary_table_includes_price_coverage() -> None:
    covered = replace(
        _result(),
        priced_symbols=("AAPL", "MSFT"),
        universe_member_peak=504,
        missing_price_count=747,
    )
    values = dict(zip(summary_table(covered)["Metric"], summary_table(covered)["Value"], strict=True))
    assert values["Symbols with prices"] == "AAPL, MSFT"
    assert values["PIT universe (peak)"] == "504"
    assert values["Missing prices"] == "747"


@pytest.mark.unit
def test_coverage_table_reads_application_snapshot() -> None:
    snapshot = DataCoverageSnapshot(
        universe_member_peak=506,
        universe_members=749,
        market_data_available=2,
        missing_market_data=747,
        insufficient_history=1,
        momentum_eligible=8,
        selected=8,
        warning="Historical S&P 500 membership is applied.",
    )
    result = replace(_result(), universe_kind=HISTORICAL_SP500, coverage=snapshot)
    table = coverage_table(result)
    values = dict(zip(table["Metric"], table["Value"], strict=True))
    assert values["Universe"] == "Historical S&P 500 Point-in-Time"
    assert values["PIT Universe Members"] == "506"
    assert values["Unique constituents"] == "749"
    assert values["Market Data Available"] == "2"
    assert values["Missing Market Data"] == "747"
    assert values["Insufficient History"] == "1"
    assert values["Momentum Eligible"] == "8"
    assert values["Selected"] == "8"

    summary = dict(zip(summary_table(result)["Metric"], summary_table(result)["Value"], strict=True))
    assert summary["PIT Universe Members"] == "506"
    assert summary["Market Data Available"] == "2"
    assert "Universe warning" not in summary


@pytest.mark.unit
def test_summary_table_historical_and_current_universe_labels() -> None:
    historical = replace(_result(), universe_kind=HISTORICAL_SP500)
    values = dict(zip(summary_table(historical)["Metric"], summary_table(historical)["Value"], strict=True))
    assert values["Universe"] == "Historical S&P 500 Point-in-Time"
    assert "Universe warning" not in values

    current = replace(_result(), universe_kind=CURRENT)
    values = dict(zip(summary_table(current)["Metric"], summary_table(current)["Value"], strict=True))
    assert values["Universe"] == "current"
    assert values["Universe warning"] == CURRENT_UNIVERSE_WARNING


@pytest.mark.unit
def test_rebalance_diagnostics_table_rows() -> None:
    result = replace(
        _result(),
        rebalance_diagnostics=(
            RebalanceDiagnostics(
                as_of=date(2020, 1, 2),
                universe_members=505,
                missing_market_data=17,
                insufficient_history=23,
                failed_price_filter=4,
                failed_liquidity_filter=8,
                momentum_eligible=184,
                selected=10,
            ),
        ),
    )
    table = rebalance_diagnostics_table(result)
    assert list(table.columns) == [
        "Rebalance",
        "Universe Members",
        "Missing Market Data",
        "Insufficient History",
        "Failed Price Filter",
        "Failed Liquidity Filter",
        "Momentum Eligible",
        "Selected",
    ]
    assert table.iloc[0]["Rebalance"] == "2020-01-02"
    assert table.iloc[0]["Universe Members"] == 505
    assert table.iloc[0]["Selected"] == 10


@pytest.mark.unit
def test_equity_table_converts_drawdown_and_returns_to_percent() -> None:
    table = equity_table(_result())
    assert list(table.columns) == ["Date", "Equity", "Cash", "Drawdown %", "Daily Return %"]
    assert table.iloc[1]["Equity"] == pytest.approx(105000.50)
    assert table.iloc[1]["Drawdown %"] == pytest.approx(-1.0)
    assert table.iloc[1]["Daily Return %"] == pytest.approx(5.0)


@pytest.mark.unit
def test_fills_table_rows() -> None:
    table = fills_table(_result())
    assert list(table.columns) == ["Time", "Symbol", "Quantity", "Price", "Commission"]
    assert table.iloc[0]["Symbol"] == "AAPL"
    assert table.iloc[0]["Quantity"] == pytest.approx(10.0)
    assert table.iloc[0]["Price"] == pytest.approx(150.25)


@pytest.mark.unit
def test_empty_fills_and_equity_tables() -> None:
    empty = BacktestResult(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),
        initial_capital=Decimal("100000"),
        final_equity=Decimal("100000"),
        total_return=0.0,
        annualized_return=0.0,
        volatility=0.0,
        sharpe_ratio=0.0,
        max_drawdown=0.0,
        number_of_trades=0,
        winning_trades=0,
        losing_trades=0,
        total_commission=Decimal("0"),
        total_slippage=Decimal("0"),
    )
    assert equity_table(empty).empty
    assert fills_table(empty).empty
    assert "SPY Buy & Hold" not in set(summary_table(empty)["Metric"])


@pytest.mark.unit
def test_dashboard_page_loads() -> None:
    from streamlit.testing.v1 import AppTest

    dashboard = Path(__file__).resolve().parents[3] / "app" / "ui" / "dashboard.py"
    app = AppTest.from_file(str(dashboard))
    app.run()
    assert not app.exception
    assert app.title[0].value == "Momentum Backtest"
