"""Strategy evaluation counts. Universe-agnostic; no membership semantics."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.models.signal import MomentumSignal


@dataclass(frozen=True)
class StrategyFilterCounts:
    """Per-rebalance filter outcomes for symbols that had market data.

    Missing prices are tracked by the backtest engine, not here.
    """

    insufficient_history: int = 0
    failed_price_filter: int = 0
    failed_liquidity_filter: int = 0
    momentum_eligible: int = 0
    selected: int = 0


@dataclass(frozen=True)
class StrategyEvaluation:
    signals: list[MomentumSignal]
    counts: StrategyFilterCounts = field(default_factory=StrategyFilterCounts)

    @property
    def selected_symbols(self) -> tuple[str, ...]:
        return tuple(signal.symbol for signal in self.signals)


def counts_from_signals(signals: Sequence[MomentumSignal]) -> StrategyFilterCounts:
    n = len(signals)
    return StrategyFilterCounts(momentum_eligible=n, selected=n)
