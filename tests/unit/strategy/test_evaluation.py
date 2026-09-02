from datetime import date
from decimal import Decimal

import pytest

from app.strategy.momentum import MomentumStrategy
from tests.fixtures.momentum import TEST_CONFIG, history_as_of, make_series, universe_market_data


@pytest.mark.unit
def test_evaluate_counts_filter_stages() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = {
        "NVDA": universe_market_data()["NVDA"],
        "SHORT": make_series("SHORT", 3),
        "CHEAP": make_series("CHEAP", 20, close=Decimal("5")),
        "ILLIQ": make_series("ILLIQ", 20, close=Decimal("50"), volume=1),
    }
    evaluation = MomentumStrategy(TEST_CONFIG).evaluate(market_data, as_of)
    assert evaluation.counts.insufficient_history == 1
    assert evaluation.counts.failed_price_filter == 1
    assert evaluation.counts.failed_liquidity_filter == 1
    assert evaluation.counts.momentum_eligible == 1
    assert evaluation.counts.selected == 1
    assert evaluation.selected_symbols == ("NVDA",)


@pytest.mark.unit
def test_generate_signals_matches_evaluate() -> None:
    as_of = history_as_of(TEST_CONFIG.lookback_days)
    market_data = universe_market_data()
    strategy = MomentumStrategy(TEST_CONFIG)
    assert strategy.generate_signals(market_data, as_of) == strategy.evaluate(market_data, as_of).signals
