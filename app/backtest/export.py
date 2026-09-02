"""Backtest result CSV exporters.

Fills and orders are written as separate files. There is no Trade type; the UI
metric Trades equals the fill count.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from app.backtest.result import BacktestResult
from app.domain.enums import OrderSide
from app.domain.models.fill import Fill
from app.domain.models.order import Order

FILLS_FIELDS = (
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "price",
    "gross_value",
    "commission",
    "slippage",
    "net_value",
    "order_id",
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


def fills_rows(result: BacktestResult) -> list[dict[str, str]]:
    orders_by_id = {order.client_order_id: order for order in result.orders}
    return [fill_row(fill, orders_by_id.get(fill.order_id)) for fill in result.fills]


def fill_row(fill: Fill, order: Order | None) -> dict[str, str]:
    side = order.side if order is not None else None
    gross = fill.quantity * fill.price
    net = _net_value(side, gross, fill.commission)
    return {
        "timestamp": fill.timestamp.isoformat(),
        "symbol": fill.symbol,
        "side": side.value if side is not None else "",
        "quantity": _decimal(fill.quantity),
        "price": _decimal(fill.price),
        "gross_value": _decimal(gross),
        "commission": _decimal(fill.commission),
        "slippage": _decimal(fill.slippage),
        "net_value": _decimal(net) if net is not None else "",
        "order_id": fill.order_id,
        "cash": _decimal(fill.cash) if fill.cash is not None else "",
        "position_quantity": (
            _decimal(fill.position_quantity) if fill.position_quantity is not None else ""
        ),
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


def fills_csv_text(result: BacktestResult) -> str:
    return _csv_text(FILLS_FIELDS, fills_rows(result))


def orders_csv_text(result: BacktestResult) -> str:
    return _csv_text(ORDERS_FIELDS, orders_rows(result))


def write_fills_csv(path: Path, result: BacktestResult) -> None:
    _write_csv(path, FILLS_FIELDS, fills_rows(result))


def write_orders_csv(path: Path, result: BacktestResult) -> None:
    _write_csv(path, ORDERS_FIELDS, orders_rows(result))


def write_backtest_export(directory: Path, result: BacktestResult) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    fills_path = directory / "fills.csv"
    orders_path = directory / "orders.csv"
    write_fills_csv(fills_path, result)
    write_orders_csv(orders_path, result)
    return fills_path, orders_path


def _net_value(side: OrderSide | None, gross: Decimal, commission: Decimal) -> Decimal | None:
    if side is None:
        return None
    if side == OrderSide.BUY:
        return -(gross + commission)
    return gross - commission


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _csv_text(fields: Sequence[str], rows: Sequence[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
