from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtest.export import (
    EQUITY_FIELDS,
    FILLS_FIELDS,
    ORDERS_FIELDS,
    equity_csv_text,
    fills_csv_text,
    orders_csv_text,
    write_backtest_export,
)
from app.backtest.result import BacktestResult
from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.models.equity import EquityPoint
from app.domain.models.fill import Fill
from app.domain.models.order import Order

UTC = timezone.utc


def _result() -> BacktestResult:
    order = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="2024-02-02-0001",
        status=OrderStatus.FILLED,
    )
    fill = Fill(
        order_id="2024-02-02-0001",
        symbol="AAPL",
        quantity=Decimal("10"),
        price=Decimal("100.10"),
        commission=Decimal("0.50"),
        timestamp=datetime(2024, 2, 2, 14, 30, tzinfo=UTC),
        slippage=Decimal("1.00"),
        cash=Decimal("98998.50"),
        position_quantity=Decimal("10"),
        market_price=Decimal("100"),
        portfolio_value=Decimal("99999.50"),
    )
    return BacktestResult(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 21),
        initial_capital=Decimal("100000"),
        final_equity=Decimal("99999.50"),
        total_return=-0.000005,
        annualized_return=0.0,
        volatility=0.0,
        sharpe_ratio=0.0,
        max_drawdown=0.0,
        number_of_trades=1,
        winning_trades=0,
        losing_trades=0,
        total_commission=Decimal("0.50"),
        total_slippage=Decimal("1.00"),
        equity_curve=(
            EquityPoint(
                date=date(2024, 2, 2),
                equity=Decimal("99999.50"),
                cash=Decimal("98998.50"),
                returns=Decimal("0"),
                drawdown=Decimal("0"),
            ),
        ),
        fills=(fill,),
        orders=(order,),
    )


@pytest.mark.backtest
def test_fills_export_schema_and_values() -> None:
    text = fills_csv_text(_result())
    header = text.splitlines()[0]
    assert header.split(",") == list(FILLS_FIELDS)
    columns = header.split(",")
    assert "fill_price" in columns
    assert "market_price" in columns
    assert "portfolio_value" in columns
    assert "net_value" not in columns
    assert columns.count("fill_price") == 1
    row = text.splitlines()[1]
    assert "AAPL" in row
    assert "BUY" in row
    assert "100.10" in row
    assert "2024-02-02-0001" in row


@pytest.mark.backtest
def test_orders_and_equity_export_schema() -> None:
    orders = orders_csv_text(_result())
    equity = equity_csv_text(_result())
    assert orders.splitlines()[0].split(",") == list(ORDERS_FIELDS)
    assert equity.splitlines()[0].split(",") == list(EQUITY_FIELDS)
    assert "FILLED" in orders
    assert "99999.50" in equity
    assert "98998.50" in equity


@pytest.mark.backtest
def test_write_backtest_export_writes_three_files(tmp_path: Path) -> None:
    fills_path, orders_path, equity_path = write_backtest_export(tmp_path, _result())
    assert fills_path.name == "fills.csv"
    assert orders_path.name == "orders.csv"
    assert equity_path.name == "equity_curve.csv"
    assert fills_path.read_text(encoding="utf-8") == fills_csv_text(_result())
    assert orders_path.read_text(encoding="utf-8") == orders_csv_text(_result())
    assert equity_path.read_text(encoding="utf-8") == equity_csv_text(_result())
