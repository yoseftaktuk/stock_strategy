from pathlib import Path

import pytest


FORBIDDEN_STRATEGY_UNIVERSE_IMPORTS = (
    "app.universe.providers.sp500",
    "SP500HistoricalSource",
)


@pytest.mark.unit
def test_strategy_does_not_import_sp500_source() -> None:
    strategy_root = Path("app/strategy")
    for path in strategy_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_STRATEGY_UNIVERSE_IMPORTS:
            assert token not in text, f"{path} references {token}"


@pytest.mark.unit
def test_backtest_does_not_import_sp500_source_adapter() -> None:
    backtest_root = Path("app/backtest")
    for path in backtest_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "app.universe.providers.sp500" not in text
        assert "SP500HistoricalSource" not in text
        assert "urllib" not in text
        assert "yfinance" not in text
