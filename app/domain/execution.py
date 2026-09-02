from decimal import Decimal

from app.domain.enums import OrderSide

BPS_DIVISOR = Decimal("10000")


def apply_slippage(side: OrderSide, market_price: Decimal, slippage_bps: Decimal) -> Decimal:
    """Return the simulated fill price after slippage.

    BUY:  market * (1 + bps/10000)
    SELL: market * (1 - bps/10000)
    """
    adjustment = slippage_bps / BPS_DIVISOR
    if side == OrderSide.BUY:
        return market_price * (Decimal("1") + adjustment)
    return market_price * (Decimal("1") - adjustment)


def commission_on(trade_value: Decimal, commission_rate: Decimal) -> Decimal:
    """Return commission as a fraction of trade value. Never negative."""
    if trade_value <= 0 or commission_rate <= 0:
        return Decimal("0")
    return trade_value * commission_rate
