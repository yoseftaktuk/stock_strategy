from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.backtest.exceptions import BacktestConfigError
from app.domain.enums import RebalanceFrequency


@dataclass(frozen=True)
class BacktestConfig:
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("100000")
    rebalance_frequency: RebalanceFrequency = RebalanceFrequency.MONTHLY
    commission_rate: Decimal = Decimal("0.0005")
    slippage_bps: Decimal = Decimal("10")
    min_trade_value: Decimal = Decimal("100")
    risk_free_rate: Decimal = Decimal("0")
    symbols: tuple[str, ...] = field(default_factory=tuple)
    warmup_sessions: int = 253
    universe_kind: str | None = None

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise BacktestConfigError("start_date must be <= end_date")
        if self.initial_capital <= 0:
            raise BacktestConfigError("initial_capital must be > 0")
        if self.commission_rate < 0:
            raise BacktestConfigError("commission_rate must be >= 0")
        if self.slippage_bps < 0:
            raise BacktestConfigError("slippage_bps must be >= 0")
        if self.min_trade_value < 0:
            raise BacktestConfigError("min_trade_value must be >= 0")
        if self.risk_free_rate < 0:
            raise BacktestConfigError("risk_free_rate must be >= 0")
        if self.warmup_sessions <= 0:
            raise BacktestConfigError("warmup_sessions must be > 0")
        if self.rebalance_frequency != RebalanceFrequency.MONTHLY:
            raise NotImplementedError(
                f"rebalance frequency {self.rebalance_frequency.value} is not implemented"
            )
