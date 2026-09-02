from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.enums import OrderSide, OrderStatus
from app.domain.execution import apply_slippage, commission_on
from app.domain.models.fill import Fill
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position

UTC = timezone.utc


class SimulatedBroker:
    def __init__(
        self,
        *,
        initial_capital: Decimal = Decimal("100000"),
        commission_rate: Decimal = Decimal("0.0005"),
        slippage_bps: Decimal = Decimal("10"),
    ) -> None:
        self._connected = False
        self._cash = initial_capital
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._fills: list[Fill] = []
        self._market_prices: dict[str, Decimal] = {}
        self._session_time = datetime(1970, 1, 1, tzinfo=UTC)
        self._commission_rate = commission_rate
        self._slippage_bps = slippage_bps
        self._total_commission = Decimal("0")
        self._total_slippage = Decimal("0")
        self._winning_trades = 0
        self._losing_trades = 0

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def set_market_prices(
        self,
        prices: Mapping[str, Decimal],
        session_time: datetime,
    ) -> None:
        self._market_prices = dict(prices)
        self._session_time = session_time

    def mark_to_market(
        self,
        prices: Mapping[str, Decimal],
        *,
        unvalued: Collection[str] = frozenset(),
    ) -> None:
        updated: dict[str, Position] = {}
        for symbol, position in self._positions.items():
            if symbol in unvalued:
                updated[symbol] = replace(position, valued=False)
                continue
            market_price = prices.get(symbol, position.market_price)
            updated[symbol] = replace(position, market_price=market_price, valued=True)
        self._positions = updated

    def get_account(self) -> Portfolio:
        return Portfolio(cash=self._cash, positions=tuple(self._positions.values()))

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_open_orders(self) -> list[Order]:
        open_statuses = {OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.SUBMITTED}
        return [order for order in self._orders if order.status in open_statuses]

    def get_fills(self) -> list[Fill]:
        return list(self._fills)

    @property
    def total_commission(self) -> Decimal:
        return self._total_commission

    @property
    def total_slippage(self) -> Decimal:
        return self._total_slippage

    @property
    def winning_trades(self) -> int:
        return self._winning_trades

    @property
    def losing_trades(self) -> int:
        return self._losing_trades

    def submit_order(self, order: Order) -> Order:
        if not self._connected:
            rejected = replace(order, status=OrderStatus.REJECTED)
            self._orders.append(rejected)
            return rejected

        validated = replace(order, status=OrderStatus.VALIDATED)
        submitted = replace(validated, status=OrderStatus.SUBMITTED)
        market_price = self._market_prices.get(order.symbol)
        if market_price is None or market_price <= 0:
            rejected = replace(submitted, status=OrderStatus.REJECTED)
            self._orders.append(rejected)
            return rejected

        fill_price = apply_slippage(order.side, market_price, self._slippage_bps)
        trade_value = order.quantity * fill_price
        commission = commission_on(trade_value, self._commission_rate)

        if order.side == OrderSide.BUY:
            filled = self._fill_buy(submitted, fill_price, trade_value, commission, market_price)
        else:
            filled = self._fill_sell(submitted, fill_price, trade_value, commission, market_price)
        self._orders.append(filled)
        return filled

    def cancel_order(self, client_order_id: str) -> None:
        updated: list[Order] = []
        for order in self._orders:
            if (
                order.client_order_id == client_order_id
                and order.status
                in {OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.SUBMITTED}
            ):
                updated.append(replace(order, status=OrderStatus.CANCELLED))
            else:
                updated.append(order)
        self._orders = updated

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        for order in reversed(self._orders):
            if order.client_order_id == client_order_id:
                return order.status
        return OrderStatus.FAILED

    def _fill_buy(
        self,
        order: Order,
        fill_price: Decimal,
        trade_value: Decimal,
        commission: Decimal,
        market_price: Decimal,
    ) -> Order:
        cost = trade_value + commission
        if cost > self._cash:
            return replace(order, status=OrderStatus.REJECTED)

        existing = self._positions.get(order.symbol)
        new_qty = order.quantity if existing is None else existing.quantity + order.quantity
        if existing is None or existing.quantity == 0:
            average_price = fill_price
        else:
            average_price = (
                existing.quantity * existing.average_price + order.quantity * fill_price
            ) / new_qty
        self._positions[order.symbol] = Position(
            symbol=order.symbol,
            quantity=new_qty,
            average_price=average_price,
            market_price=fill_price,
        )
        self._cash -= cost
        self._record_fill(order, fill_price, commission, market_price)
        return replace(order, status=OrderStatus.FILLED)

    def _fill_sell(
        self,
        order: Order,
        fill_price: Decimal,
        trade_value: Decimal,
        commission: Decimal,
        market_price: Decimal,
    ) -> Order:
        existing = self._positions.get(order.symbol)
        if existing is None or order.quantity > existing.quantity:
            return replace(order, status=OrderStatus.REJECTED)

        if fill_price > existing.average_price:
            self._winning_trades += 1
        elif fill_price < existing.average_price:
            self._losing_trades += 1

        remaining = existing.quantity - order.quantity
        if remaining == 0:
            del self._positions[order.symbol]
        else:
            self._positions[order.symbol] = replace(
                existing,
                quantity=remaining,
                market_price=fill_price,
            )
        self._cash += trade_value - commission
        self._record_fill(order, fill_price, commission, market_price)
        return replace(order, status=OrderStatus.FILLED)

    def _record_fill(
        self,
        order: Order,
        fill_price: Decimal,
        commission: Decimal,
        market_price: Decimal,
    ) -> None:
        slippage = abs(fill_price - market_price) * order.quantity
        position = self._positions.get(order.symbol)
        position_quantity = position.quantity if position is not None else Decimal("0")
        account = self.get_account()
        fill = Fill(
            order_id=order.client_order_id,
            symbol=order.symbol,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            timestamp=self._session_time,
            slippage=slippage,
            cash=self._cash,
            position_quantity=position_quantity,
            market_price=market_price,
            portfolio_value=account.equity,
        )
        self._fills.append(fill)
        self._total_commission += commission
        self._total_slippage += slippage
