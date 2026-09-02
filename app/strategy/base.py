from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import date

from app.domain.models.market_bar import MarketBar
from app.domain.models.signal import MomentumSignal
from app.strategy.evaluation import StrategyEvaluation, counts_from_signals


class Strategy(ABC):
    @abstractmethod
    def generate_signals(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> list[MomentumSignal]:
        """Generate trading signals from market data as of ``as_of``."""

    def evaluate(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> StrategyEvaluation:
        """Return signals plus filter counts. Default wraps ``generate_signals``."""
        signals = self.generate_signals(market_data, as_of)
        return StrategyEvaluation(signals=signals, counts=counts_from_signals(signals))
