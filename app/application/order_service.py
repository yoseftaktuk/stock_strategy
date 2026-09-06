from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

from app.domain.enums import OrderSide, OrderType
from app.domain.execution import apply_slippage, commission_on
from app.domain.models.identity import IdentityRef, position_key_for
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio
from app.domain.models.target import TargetPortfolio


@dataclass
class _Booked:
    execution_symbol: str
    quantity: Decimal
    market_value: Decimal
    identity: IdentityRef | None
    target_weight: Decimal


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
        booked = _booked_by_position_key(current, target)
        keys = sorted(booked)

        sell_intents: list[tuple[str, Decimal]] = []
        buy_intents: list[tuple[str, Decimal]] = []

        for key in keys:
            slot = booked[key]
            symbol = slot.execution_symbol
            market_price = prices.get(symbol)
            if market_price is None or market_price <= 0:
                continue
            target_value = equity * slot.target_weight
            held_value = slot.market_value
            if abs(target_value - held_value) < min_trade_value:
                continue

            side = OrderSide.BUY if target_value >= held_value else OrderSide.SELL
            execution_price = apply_slippage(side, market_price, self._slippage_bps)
            if execution_price <= 0:
                continue
            target_shares = (target_value / execution_price).to_integral_value(rounding=ROUND_DOWN)
            held_shares = slot.quantity
            delta = target_shares - held_shares
            if delta < 0:
                sell_qty = min(-delta, held_shares)
                if sell_qty > 0:
                    sell_intents.append((key, sell_qty))
            elif delta > 0:
                buy_intents.append((key, delta))

        projected_cash = current.cash
        for key, quantity in sell_intents:
            symbol = booked[key].execution_symbol
            fill_price = apply_slippage(OrderSide.SELL, prices[symbol], self._slippage_bps)
            trade_value = quantity * fill_price
            projected_cash += trade_value - commission_on(trade_value, self._commission_rate)

        affordable_buys: list[tuple[str, Decimal]] = []
        for key, quantity in buy_intents:
            symbol = booked[key].execution_symbol
            fill_price = apply_slippage(OrderSide.BUY, prices[symbol], self._slippage_bps)
            affordable = _max_shares_for_cash(projected_cash, fill_price, self._commission_rate)
            quantity = min(quantity, affordable)
            if quantity <= 0:
                continue
            trade_value = quantity * fill_price
            if trade_value < min_trade_value:
                continue
            projected_cash -= trade_value + commission_on(trade_value, self._commission_rate)
            affordable_buys.append((key, quantity))

        orders: list[Order] = []
        sequence = 1
        for key, quantity in sell_intents:
            slot = booked[key]
            orders.append(
                _market_order(
                    slot.execution_symbol,
                    OrderSide.SELL,
                    quantity,
                    as_of,
                    sequence,
                    identity=slot.identity,
                )
            )
            sequence += 1
        for key, quantity in affordable_buys:
            slot = booked[key]
            orders.append(
                _market_order(
                    slot.execution_symbol,
                    OrderSide.BUY,
                    quantity,
                    as_of,
                    sequence,
                    identity=slot.identity,
                )
            )
            sequence += 1
        return orders


def _booked_by_position_key(
    current: Portfolio,
    target: TargetPortfolio,
) -> dict[str, _Booked]:
    booked: dict[str, _Booked] = {}
    for position in current.positions:
        key = position_key_for(position)
        booked[key] = _Booked(
            execution_symbol=position.symbol,
            quantity=position.quantity,
            market_value=position.market_value,
            identity=position.identity,
            target_weight=Decimal("0"),
        )
    for item in target.positions:
        key = position_key_for(item)
        existing = booked.get(key)
        if existing is None:
            booked[key] = _Booked(
                execution_symbol=item.symbol,
                quantity=Decimal("0"),
                market_value=Decimal("0"),
                identity=item.identity,
                target_weight=item.target_weight,
            )
            continue
        booked[key] = _Booked(
            execution_symbol=item.symbol,
            quantity=existing.quantity,
            market_value=existing.market_value,
            identity=item.identity if item.identity is not None else existing.identity,
            target_weight=item.target_weight,
        )
    return booked


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
    *,
    identity: IdentityRef | None,
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=f"{as_of.isoformat()}-{sequence:04d}",
        identity=identity,
    )
