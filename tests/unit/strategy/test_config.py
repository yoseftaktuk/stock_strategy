from decimal import Decimal
from pathlib import Path

import pytest

from app.strategy.config import MomentumConfig
from app.strategy.exceptions import StrategyConfigError


@pytest.mark.unit
def test_default_config_values() -> None:
    config = MomentumConfig()
    assert config.lookback_days == 252
    assert config.skip_days == 21
    assert config.top_n == 10
    assert config.min_price == Decimal("10")
    assert config.liquidity_window_days == 20
    assert config.min_dollar_volume == Decimal("20000000")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"lookback_days": 21, "skip_days": 21}, "lookback_days must be > skip_days"),
        ({"lookback_days": 10, "skip_days": 21}, "lookback_days must be > skip_days"),
        ({"skip_days": -1}, "skip_days must be >= 0"),
        ({"top_n": 0}, "top_n must be > 0"),
        ({"top_n": -3}, "top_n must be > 0"),
        ({"min_price": Decimal("-0.01")}, "min_price must be >= 0"),
        ({"min_dollar_volume": Decimal("-1")}, "min_dollar_volume must be >= 0"),
        ({"liquidity_window_days": 0}, "liquidity_window_days must be > 0"),
        ({"liquidity_window_days": -5}, "liquidity_window_days must be > 0"),
    ],
)
def test_invalid_configurations_fail_validation(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises(StrategyConfigError, match=match):
        MomentumConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_strategy_package_has_no_circular_imports() -> None:
    from app.strategy.calculations import calculate_momentum
    from app.strategy.config import MomentumConfig as Config
    from app.strategy.filters import PriceFilter
    from app.strategy.momentum import MomentumStrategy
    from app.strategy.ranking import rank_candidates

    assert calculate_momentum is not None
    assert Config is not None
    assert PriceFilter is not None
    assert MomentumStrategy is not None
    assert rank_candidates is not None


@pytest.mark.unit
def test_strategy_modules_exist() -> None:
    root = Path("app/strategy")
    expected = {
        "base.py",
        "calculations.py",
        "config.py",
        "exceptions.py",
        "filters.py",
        "momentum.py",
        "ranking.py",
    }
    present = {path.name for path in root.glob("*.py")}
    assert expected <= present
