from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.enums import OrderStatus
from app.domain.models.fill import Fill
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position


class Broker(Protocol):
    def connect(self) -> None:
        """Establish connection to the broker."""

    def disconnect(self) -> None:
        """Close connection to the broker."""

    def is_connected(self) -> bool:
        """Return whether the broker connection is active."""

    def get_account(self) -> Portfolio:
        """Return the current account portfolio."""

    def get_positions(self) -> list[Position]:
        """Return current open positions."""

    def get_open_orders(self) -> list[Order]:
        """Return currently open orders."""

    def submit_order(self, order: Order) -> Order:
        """Submit an order to the broker."""

    def cancel_order(self, client_order_id: str) -> None:
        """Cancel an open order."""

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        """Return the current status of an order."""


class SessionAwareBroker(Broker, Protocol):
    """Broker that can ingest session prices for backtests."""

    def set_market_prices(
        self,
        prices: Mapping[str, Decimal],
        session_time: datetime,
    ) -> None:
        """Set execution-session market prices (typically opens)."""

    def mark_to_market(self, prices: Mapping[str, Decimal]) -> None:
        """Update position market prices without trading."""


class BacktestBroker(SessionAwareBroker, Protocol):
    """Session-aware broker that exposes fill statistics for backtests."""

    def get_fills(self) -> list[Fill]:
        """Return recorded fills."""

    @property
    def total_commission(self) -> Decimal:
        """Cumulative commission paid."""

    @property
    def total_slippage(self) -> Decimal:
        """Cumulative slippage cost."""

    @property
    def winning_trades(self) -> int:
        """Closed sells filled above average cost."""

    @property
    def losing_trades(self) -> int:
        """Closed sells filled below average cost."""
