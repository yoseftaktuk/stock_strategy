from collections.abc import Sequence
from decimal import Decimal

from app.domain.models.signal import MomentumSignal
from app.domain.models.target import TargetPortfolio, TargetPosition


class PortfolioService:
    def build_target_portfolio(self, signals: Sequence[MomentumSignal]) -> TargetPortfolio:
        eligible = [signal for signal in signals if signal.eligible]
        if not eligible:
            return TargetPortfolio(positions=(), cash_weight=Decimal("1"))

        count = Decimal(len(eligible))
        weight = Decimal("1") / count
        positions = tuple(
            TargetPosition(symbol=signal.symbol, target_weight=weight) for signal in eligible
        )
        invested = weight * count
        cash_weight = Decimal("1") - invested
        return TargetPortfolio(positions=positions, cash_weight=cash_weight)
