from collections.abc import Mapping, Sequence
from datetime import date
import logging

from app.domain.models.market_bar import MarketBar
from app.domain.models.signal import MomentumSignal
from app.strategy.base import Strategy
from app.strategy.calculations import calculate_momentum
from app.strategy.config import MomentumConfig
from app.strategy.evaluation import StrategyEvaluation, StrategyFilterCounts
from app.strategy.exceptions import StrategyDataError
from app.strategy.filters import LiquidityFilter, MomentumFilter, PriceFilter
from app.strategy.ranking import MomentumCandidate, rank_candidates, select_top_n

logger = logging.getLogger(__name__)

_INSUFFICIENT_HISTORY = "insufficient_history"
_FAILED_PRICE = "failed_price_filter"
_FAILED_LIQUIDITY = "failed_liquidity_filter"
_ELIGIBLE = "eligible"


class MomentumStrategy(Strategy):
    def __init__(self, config: MomentumConfig) -> None:
        self._config = config
        self._price_filter = PriceFilter(config.min_price)
        self._liquidity_filter = LiquidityFilter(
            window_days=config.liquidity_window_days,
            min_dollar_volume=config.min_dollar_volume,
        )
        self._momentum_filter = MomentumFilter()

    @property
    def config(self) -> MomentumConfig:
        return self._config

    def generate_signals(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> list[MomentumSignal]:
        return self.evaluate(market_data, as_of).signals

    def evaluate(
        self,
        market_data: Mapping[str, Sequence[MarketBar]],
        as_of: date,
    ) -> StrategyEvaluation:
        candidates: list[MomentumCandidate] = []
        insufficient_history = 0
        failed_price_filter = 0
        failed_liquidity_filter = 0
        for symbol, bars in market_data.items():
            candidate, disposition = self._evaluate_symbol(symbol, bars, as_of)
            if disposition == _INSUFFICIENT_HISTORY:
                insufficient_history += 1
            elif disposition == _FAILED_PRICE:
                failed_price_filter += 1
            elif disposition == _FAILED_LIQUIDITY:
                failed_liquidity_filter += 1
            if candidate is not None:
                candidates.append(candidate)

        ranked = rank_candidates(candidates)
        selected = select_top_n(ranked, self._config.top_n)
        logger.info(
            "Momentum candidates=%s selected=%s as_of=%s",
            len(candidates),
            len(selected),
            as_of.isoformat(),
        )
        signals = [
            MomentumSignal(
                symbol=candidate.symbol,
                date=candidate.date,
                momentum=candidate.momentum,
                rank=rank,
                eligible=True,
            )
            for rank, candidate in enumerate(selected, start=1)
        ]
        return StrategyEvaluation(
            signals=signals,
            counts=StrategyFilterCounts(
                insufficient_history=insufficient_history,
                failed_price_filter=failed_price_filter,
                failed_liquidity_filter=failed_liquidity_filter,
                momentum_eligible=len(candidates),
                selected=len(selected),
            ),
        )

    def _evaluate_symbol(
        self,
        symbol: str,
        bars: Sequence[MarketBar],
        as_of: date,
    ) -> tuple[MomentumCandidate | None, str | None]:
        try:
            sliced = _slice_as_of(bars, as_of)
            if len(sliced) < self._config.lookback_days + 1:
                logger.warning(
                    "Skipping symbol=%s reason=insufficient history need=%s got=%s",
                    symbol,
                    self._config.lookback_days + 1,
                    len(sliced),
                )
                return None, _INSUFFICIENT_HISTORY

            price_result = self._price_filter.is_eligible(sliced)
            if not price_result.passed:
                logger.warning("Skipping symbol=%s reason=%s", symbol, price_result.reason)
                return None, _FAILED_PRICE

            liquidity_result = self._liquidity_filter.is_eligible(sliced)
            if not liquidity_result.passed:
                logger.warning(
                    "Skipping symbol=%s reason=%s",
                    symbol,
                    liquidity_result.reason,
                )
                return None, _FAILED_LIQUIDITY

            momentum = calculate_momentum(
                sliced,
                lookback_days=self._config.lookback_days,
                skip_days=self._config.skip_days,
            )
            momentum_result = self._momentum_filter.is_eligible(momentum)
            if not momentum_result.passed:
                logger.warning(
                    "Skipping symbol=%s reason=%s",
                    symbol,
                    momentum_result.reason,
                )
                return None, None

            return MomentumCandidate(symbol=symbol, date=as_of, momentum=momentum), _ELIGIBLE
        except StrategyDataError as exc:
            logger.warning("Skipping symbol=%s reason=%s", symbol, exc)
            return None, None
        except Exception:
            logger.exception("Skipping symbol=%s reason=malformed data", symbol)
            return None, None


def _slice_as_of(bars: Sequence[MarketBar], as_of: date) -> list[MarketBar]:
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    return [bar for bar in ordered if bar.timestamp.date() <= as_of]
