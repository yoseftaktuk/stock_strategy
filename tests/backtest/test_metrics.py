from datetime import date
from decimal import Decimal
import math
import statistics

import pytest

from app.backtest.metrics import CALENDAR_DAYS_PER_YEAR, MetricsCalculator
from app.domain.models.equity import EquityPoint


def _curve() -> list[EquityPoint]:
    values = [Decimal("100"), Decimal("110"), Decimal("105"), Decimal("120")]
    dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    peak = values[0]
    points: list[EquityPoint] = []
    previous = values[0]
    for index, (session, equity) in enumerate(zip(dates, values, strict=True)):
        daily_return = Decimal("0") if index == 0 else equity / previous - 1
        if equity > peak:
            peak = equity
        points.append(
            EquityPoint(
                date=session,
                equity=equity,
                cash=equity,
                returns=daily_return,
                drawdown=equity / peak - 1,
            )
        )
        previous = equity
    return points


@pytest.mark.backtest
def test_metrics_on_known_curve() -> None:
    curve = _curve()
    metrics = MetricsCalculator().calculate(curve, Decimal("100"))
    assert metrics.total_return == pytest.approx(0.20)
    years = 3 / CALENDAR_DAYS_PER_YEAR
    expected_cagr = (1.20 ** (1 / years)) - 1
    assert metrics.annualized_return == pytest.approx(expected_cagr)

    daily = [0.10, float(Decimal("105") / Decimal("110") - 1), float(Decimal("120") / Decimal("105") - 1)]
    expected_vol = statistics.stdev(daily) * math.sqrt(252)
    expected_sharpe = (statistics.fmean(daily) / statistics.stdev(daily)) * math.sqrt(252)
    assert metrics.volatility == pytest.approx(expected_vol)
    assert metrics.sharpe_ratio == pytest.approx(expected_sharpe)
    expected_dd = float(Decimal("105") / Decimal("110") - 1)
    assert metrics.max_drawdown == pytest.approx(expected_dd)
