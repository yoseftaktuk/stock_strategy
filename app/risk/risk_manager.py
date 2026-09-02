from decimal import Decimal

from app.domain.enums import OrderSide
from app.domain.models.order import Order
from app.domain.models.portfolio import Portfolio


class RiskManager:
    def validate(self, order: Order, portfolio: Portfolio) -> bool:
        if order.side == OrderSide.SELL:
            held = next(
                (position.quantity for position in portfolio.positions if position.symbol == order.symbol),
                Decimal("0"),
            )
            if order.quantity > held:
                return False
        return True
