"""Performance metrics.

Statistical measures convert Decimal equity values to float. Prices, cash,
commissions, and trade values remain Decimal in the engine and broker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import math
import statistics

from app.domain.models.equity import EquityPoint

TRADING_DAYS_PER_YEAR = 252
CALENDAR_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float


class MetricsCalculator:
    def calculate(
        self,
        equity_curve: Sequence[EquityPoint],
        initial_capital: Decimal,
        *,
        risk_free_rate: Decimal = Decimal("0"),
        start: date | None = None,
        end: date | None = None,
    ) -> PerformanceMetrics:
        if not equity_curve or initial_capital <= 0:
            return PerformanceMetrics(
                total_return=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
            )

        final_equity = equity_curve[-1].equity
        total_return = float(final_equity / initial_capital - 1)
        first = start or equity_curve[0].date
        last = end or equity_curve[-1].date
        years = max((last - first).days, 0) / CALENDAR_DAYS_PER_YEAR
        if years <= 0:
            annualized = 0.0
        else:
            annualized = (float(final_equity / initial_capital) ** (1 / years)) - 1

        daily_returns = [float(point.returns) for point in equity_curve[1:]]
        volatility, sharpe = _vol_and_sharpe(daily_returns, float(risk_free_rate))
        max_drawdown = min((float(point.drawdown) for point in equity_curve), default=0.0)
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized,
            volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
        )


def _vol_and_sharpe(daily_returns: list[float], annual_risk_free_rate: float) -> tuple[float, float]:
    if len(daily_returns) < 2:
        return 0.0, 0.0
    stdev = statistics.stdev(daily_returns)
    if stdev == 0:
        return 0.0, 0.0
    mean = statistics.fmean(daily_returns)
    volatility = stdev * math.sqrt(TRADING_DAYS_PER_YEAR)
    daily_rf = annual_risk_free_rate / TRADING_DAYS_PER_YEAR
    sharpe = ((mean - daily_rf) / stdev) * math.sqrt(TRADING_DAYS_PER_YEAR)
    return volatility, sharpe
