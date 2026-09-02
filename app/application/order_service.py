from collections.abc import Mapping
from datetime import date
from decimal import ROUND_DOWN, Decimal

from app.domain.enums import OrderSide, OrderType
from app.domain.execution import apply_slippage, commission_on
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.target import TargetPortfolio


class OrderService:
    def __init__(
        self,
        *,
        commission_rate: Decimal = Decimal("0.0005"),
        slippage_bps: Decimal = Decimal("10"),
    ) -> None:
        self._commission_rate = commission_rate
        self._slippage_bps = slippage_bps

    def create_orders_from_targets(
        self,
        current: Portfolio,
        target: TargetPortfolio,
        prices: Mapping[str, Decimal],
        *,
        min_trade_value: Decimal,
        as_of: date,
    ) -> list[Order]:
        equity = current.equity
        current_qty = {position.symbol: position.quantity for position in current.positions}
        current_value = {position.symbol: position.market_value for position in current.positions}
        target_weights = {item.symbol: item.target_weight for item in target.positions}
        symbols = sorted(set(current_qty) | set(target_weights))

        sell_intents: list[tuple[str, Decimal]] = []
        buy_intents: list[tuple[str, Decimal]] = []

        for symbol in symbols:
            market_price = prices.get(symbol)
            if market_price is None or market_price <= 0:
                continue
            weight = target_weights.get(symbol, Decimal("0"))
            target_value = equity * weight
            held_value = current_value.get(symbol, Decimal("0"))
            if abs(target_value - held_value) < min_trade_value:
                continue

            side = OrderSide.BUY if target_value >= held_value else OrderSide.SELL
            execution_price = apply_slippage(side, market_price, self._slippage_bps)
            if execution_price <= 0:
                continue
            target_shares = (target_value / execution_price).to_integral_value(rounding=ROUND_DOWN)
            held_shares = current_qty.get(symbol, Decimal("0"))
            delta = target_shares - held_shares
            if delta < 0:
                sell_qty = min(-delta, held_shares)
                if sell_qty > 0:
                    sell_intents.append((symbol, sell_qty))
            elif delta > 0:
                buy_intents.append((symbol, delta))

        projected_cash = current.cash
        for symbol, quantity in sell_intents:
            fill_price = apply_slippage(OrderSide.SELL, prices[symbol], self._slippage_bps)
            trade_value = quantity * fill_price
            projected_cash += trade_value - commission_on(trade_value, self._commission_rate)

        affordable_buys: list[tuple[str, Decimal]] = []
        for symbol, quantity in buy_intents:
            fill_price = apply_slippage(OrderSide.BUY, prices[symbol], self._slippage_bps)
            affordable = _max_shares_for_cash(projected_cash, fill_price, self._commission_rate)
            quantity = min(quantity, affordable)
            if quantity <= 0:
                continue
            trade_value = quantity * fill_price
            if trade_value < min_trade_value:
                continue
            projected_cash -= trade_value + commission_on(trade_value, self._commission_rate)
            affordable_buys.append((symbol, quantity))

        orders: list[Order] = []
        sequence = 1
        for symbol, quantity in sell_intents:
            orders.append(_market_order(symbol, OrderSide.SELL, quantity, as_of, sequence))
            sequence += 1
        for symbol, quantity in affordable_buys:
            orders.append(_market_order(symbol, OrderSide.BUY, quantity, as_of, sequence))
            sequence += 1
        return orders


def _max_shares_for_cash(cash: Decimal, fill_price: Decimal, commission_rate: Decimal) -> Decimal:
    if fill_price <= 0 or cash <= 0:
        return Decimal("0")
    cost_per_share = fill_price * (Decimal("1") + commission_rate)
    if cost_per_share <= 0:
        return Decimal("0")
    return (cash / cost_per_share).to_integral_value(rounding=ROUND_DOWN)


def _market_order(
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    as_of: date,
    sequence: int,
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=f"{as_of.isoformat()}-{sequence:04d}",
    )
