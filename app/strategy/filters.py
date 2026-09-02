from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.models.market_bar import MarketBar
from app.strategy.calculations import calculate_average_dollar_volume
from app.strategy.exceptions import StrategyDataError


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reason: str | None = None


class PriceFilter:
    def __init__(self, min_price: Decimal) -> None:
        self._min_price = min_price

    def is_eligible(self, bars: Sequence[MarketBar]) -> FilterResult:
        if not bars:
            return FilterResult(passed=False, reason="no bars for price filter")
        close = bars[-1].close
        if close < self._min_price:
            return FilterResult(
                passed=False,
                reason=f"price {close} below min_price {self._min_price}",
            )
        return FilterResult(passed=True)


class LiquidityFilter:
    def __init__(self, window_days: int, min_dollar_volume: Decimal) -> None:
        self._window_days = window_days
        self._min_dollar_volume = min_dollar_volume

    def is_eligible(self, bars: Sequence[MarketBar]) -> FilterResult:
        try:
            average_dollar_volume = calculate_average_dollar_volume(
                bars,
                self._window_days,
            )
        except StrategyDataError as exc:
            return FilterResult(passed=False, reason=str(exc))

        if average_dollar_volume < self._min_dollar_volume:
            return FilterResult(
                passed=False,
                reason=(
                    f"average dollar volume {average_dollar_volume} below "
                    f"min_dollar_volume {self._min_dollar_volume}"
                ),
            )
        return FilterResult(passed=True)


class MomentumFilter:
    def is_eligible(self, momentum: Decimal) -> FilterResult:
        if momentum > 0:
            return FilterResult(passed=True)
        return FilterResult(
            passed=False,
            reason=f"non-positive momentum {momentum}",
        )
