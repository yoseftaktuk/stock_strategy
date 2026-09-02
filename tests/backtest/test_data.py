from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.backtest.data import max_bar_count, warmup_history_start
from tests.fixtures.momentum import make_series


@pytest.mark.backtest
def test_max_bar_count_empty() -> None:
    assert max_bar_count({}) == 0


@pytest.mark.backtest
def test_max_bar_count_uses_longest_series() -> None:
    market_data = {
        "AAPL": make_series("AAPL", 5, start=date(2025, 1, 2), close=Decimal("50")),
        "MSFT": make_series("MSFT", 2, start=date(2025, 1, 2), close=Decimal("50")),
    }
    assert max_bar_count(market_data) == 5


@pytest.mark.backtest
def test_warmup_history_start_matches_momentum_buffer() -> None:
    assert warmup_history_start(date(2015, 1, 1), 252) == date(2013, 7, 6)
    assert warmup_history_start(date(2015, 1, 1), 252) == date(2015, 1, 1) - timedelta(days=252 * 2 + 40)
