from dataclasses import dataclass
from decimal import Decimal

from app.strategy.exceptions import StrategyConfigError


@dataclass(frozen=True)
class MomentumConfig:
    lookback_days: int = 252
    skip_days: int = 21
    top_n: int = 10
    min_price: Decimal = Decimal("10")
    liquidity_window_days: int = 20
    min_dollar_volume: Decimal = Decimal("20000000")

    def __post_init__(self) -> None:
        if self.skip_days < 0:
            raise StrategyConfigError("skip_days must be >= 0")
        if self.lookback_days <= self.skip_days:
            raise StrategyConfigError("lookback_days must be > skip_days")
        if self.top_n <= 0:
            raise StrategyConfigError("top_n must be > 0")
        if self.min_price < 0:
            raise StrategyConfigError("min_price must be >= 0")
        if self.min_dollar_volume < 0:
            raise StrategyConfigError("min_dollar_volume must be >= 0")
        if self.liquidity_window_days <= 0:
            raise StrategyConfigError("liquidity_window_days must be > 0")
