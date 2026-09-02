from collections.abc import Collection, Mapping
from datetime import datetime
from decimal import Decimal

from app.broker.ibkr.client import IBKRClient
from app.domain.enums import OrderStatus
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position


class IBKRBroker:
    def __init__(self, client: IBKRClient) -> None:
        self._client = client

    def connect(self) -> None:
        self._client.connect()

    def disconnect(self) -> None:
        self._client.disconnect()

    def is_connected(self) -> bool:
        return self._client.is_connected()

    def get_account(self) -> Portfolio:
        raise NotImplementedError("IBKR integration not implemented")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("IBKR integration not implemented")

    def get_open_orders(self) -> list[Order]:
        raise NotImplementedError("IBKR integration not implemented")

    def submit_order(self, order: Order) -> Order:
        raise NotImplementedError("IBKR integration not implemented")

    def cancel_order(self, client_order_id: str) -> None:
        raise NotImplementedError("IBKR integration not implemented")

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        raise NotImplementedError("IBKR integration not implemented")

    def set_market_prices(
        self,
        prices: Mapping[str, Decimal],
        session_time: datetime,
    ) -> None:
        raise NotImplementedError("IBKR integration not implemented")

    def mark_to_market(
        self,
        prices: Mapping[str, Decimal],
        *,
        unvalued: Collection[str] = frozenset(),
    ) -> None:
        raise NotImplementedError("IBKR integration not implemented")
