"""Backtest execution CSV exporters.

Market-data CSVs under data/raw/ are OHLCV only. These files are independent:

- fills.csv — successful executions (not a Trade type)
- orders.csv — order intents, including rejected orders
- equity_curve.csv — portfolio valuation history

There is no Trade type. BacktestResult.number_of_trades equals the fill count.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from app.backtest.result import BacktestResult
from app.domain.models.fill import Fill
from app.domain.models.order import Order

FILLS_FIELDS = (
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "market_price",
    "fill_price",
    "gross_value",
    "commission",
    "slippage",
    "order_id",
    "portfolio_value",
    "cash",
    "position_quantity",
)
ORDERS_FIELDS = (
    "client_order_id",
    "symbol",
    "side",
    "quantity",
    "order_type",
    "status",
    "limit_price",
)
EQUITY_FIELDS = (
    "date",
    "equity",
    "cash",
    "returns",
    "drawdown",
)


def fills_rows(result: BacktestResult) -> list[dict[str, str]]:
    orders_by_id = {order.client_order_id: order for order in result.orders}
    return [fill_row(fill, orders_by_id.get(fill.order_id)) for fill in result.fills]


def fill_row(fill: Fill, order: Order | None) -> dict[str, str]:
    side = order.side if order is not None else None
    gross = fill.quantity * fill.price
    return {
        "timestamp": fill.timestamp.isoformat(),
        "symbol": fill.symbol,
        "side": side.value if side is not None else "",
        "quantity": _decimal(fill.quantity),
        "market_price": _optional_decimal(fill.market_price),
        "fill_price": _decimal(fill.price),
        "gross_value": _decimal(gross),
        "commission": _decimal(fill.commission),
        "slippage": _decimal(fill.slippage),
        "order_id": fill.order_id,
        "portfolio_value": _optional_decimal(fill.portfolio_value),
        "cash": _optional_decimal(fill.cash),
        "position_quantity": _optional_decimal(fill.position_quantity),
    }


def orders_rows(result: BacktestResult) -> list[dict[str, str]]:
    return [
        {
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": _decimal(order.quantity),
            "order_type": order.order_type.value,
            "status": order.status.value,
            "limit_price": _decimal(order.limit_price) if order.limit_price is not None else "",
        }
        for order in result.orders
    ]


def equity_rows(result: BacktestResult) -> list[dict[str, str]]:
    return [
        {
            "date": point.date.isoformat(),
            "equity": _decimal(point.equity),
            "cash": _decimal(point.cash),
            "returns": _decimal(point.returns),
            "drawdown": _decimal(point.drawdown),
        }
        for point in result.equity_curve
    ]


def fills_csv_text(result: BacktestResult) -> str:
    return _csv_text(FILLS_FIELDS, fills_rows(result))


def orders_csv_text(result: BacktestResult) -> str:
    return _csv_text(ORDERS_FIELDS, orders_rows(result))


def equity_csv_text(result: BacktestResult) -> str:
    return _csv_text(EQUITY_FIELDS, equity_rows(result))


def write_fills_csv(path: Path, result: BacktestResult) -> None:
    _write_csv(path, FILLS_FIELDS, fills_rows(result))


def write_orders_csv(path: Path, result: BacktestResult) -> None:
    _write_csv(path, ORDERS_FIELDS, orders_rows(result))


def write_equity_csv(path: Path, result: BacktestResult) -> None:
    _write_csv(path, EQUITY_FIELDS, equity_rows(result))


def write_backtest_export(directory: Path, result: BacktestResult) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    fills_path = directory / "fills.csv"
    orders_path = directory / "orders.csv"
    equity_path = directory / "equity_curve.csv"
    write_fills_csv(fills_path, result)
    write_orders_csv(orders_path, result)
    write_equity_csv(equity_path, result)
    return fills_path, orders_path, equity_path


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _optional_decimal(value: Decimal | None) -> str:
    return _decimal(value) if value is not None else ""


def _csv_text(fields: Sequence[str], rows: Sequence[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
