from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.backtest.data import discover_csv_symbols
from app.backtest.exceptions import EmptyUniverseError, InsufficientHistoryError
from app.backtest.runner import available_symbols, ensure_sufficient_history, resolve_universe
from app.config.settings import Settings
from tests.fixtures.momentum import make_series


@pytest.mark.backtest
def test_resolve_universe_prefers_explicit_symbols() -> None:
    settings = Settings(universe=["MSFT"], data_provider="CSV")
    assert resolve_universe(settings, ["aapl", "AAPL", " nvda "]) == ("AAPL", "NVDA")


@pytest.mark.backtest
def test_empty_universe_error_mentions_named_universe() -> None:
    error = EmptyUniverseError(
        "Universe is empty. Pass --symbol, --universe historical_sp500|current"
    )
    assert "historical_sp500" in str(error)


@pytest.mark.backtest
def test_resolve_universe_uses_settings_when_explicit_missing() -> None:
    settings = Settings(universe=["msft"], data_provider="IBKR")
    assert resolve_universe(settings) == ("MSFT",)


@pytest.mark.backtest
def test_resolve_universe_discovers_csv_when_empty(tmp_path: Path) -> None:
    header = "symbol,timestamp,open,high,low,close,adjusted_close,volume\n"
    (tmp_path / "aapl.csv").write_text(header, encoding="utf-8")
    (tmp_path / "msft_daily.csv").write_text(header, encoding="utf-8")
    settings = Settings(universe=[], data_provider="CSV", csv_data_path=str(tmp_path))
    assert resolve_universe(settings) == ("AAPL", "MSFT")


@pytest.mark.backtest
def test_available_symbols_unions_settings_and_csv(tmp_path: Path) -> None:
    (tmp_path / "NVDA.csv").write_text(
        "symbol,timestamp,open,high,low,close,adjusted_close,volume\n",
        encoding="utf-8",
    )
    settings = Settings(universe=["AAPL", "nvda"], data_provider="CSV", csv_data_path=str(tmp_path))
    assert available_symbols(settings) == ("AAPL", "NVDA")


@pytest.mark.backtest
def test_discover_csv_symbols_skips_universe_cache(tmp_path: Path) -> None:
    header = "symbol,timestamp,open,high,low,close,adjusted_close,volume\n"
    (tmp_path / "AAPL.csv").write_text(header, encoding="utf-8")
    (tmp_path / "sp500_historical.csv").write_text("date,tickers\n1996-01-02,\"AAPL,MSFT\"\n", encoding="utf-8")
    assert discover_csv_symbols(tmp_path) == ("AAPL",)
    settings = Settings(universe=[], data_provider="CSV", csv_data_path=str(tmp_path))
    assert available_symbols(settings) == ("AAPL",)
    assert "SP500_HISTORICAL" not in available_symbols(settings)


@pytest.mark.backtest
def test_ensure_sufficient_history_raises_when_short() -> None:
    market_data = {"AAPL": make_series("AAPL", 5, start=date(2025, 1, 2), close=Decimal("50"))}
    with pytest.raises(InsufficientHistoryError, match="Need at least 253") as caught:
        ensure_sufficient_history(
            market_data,
            lookback_days=252,
            start=date(2015, 1, 1),
            end=date(2025, 12, 31),
            csv_data_path="data/raw",
        )
    assert caught.value.loaded == 5
    assert caught.value.need == 253


@pytest.mark.backtest
def test_ensure_sufficient_history_passes_when_long_enough() -> None:
    market_data = {"AAPL": make_series("AAPL", 6, start=date(2024, 1, 2), close=Decimal("50"))}
    ensure_sufficient_history(
        market_data,
        lookback_days=5,
        start=date(2024, 1, 2),
        end=date(2024, 3, 1),
        csv_data_path="data/raw",
    )


@pytest.mark.backtest
def test_empty_universe_error_message() -> None:
    error = EmptyUniverseError("Universe is empty. Pass --symbol")
    assert "Universe is empty" in str(error)


@pytest.mark.backtest
def test_cli_supports_universe_and_verbose() -> None:
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "scripts/run_backtest.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--universe" in completed.stdout
    assert "historical_sp500" in completed.stdout
    assert "current" in completed.stdout
    assert "--verbose" in completed.stdout
    assert "--start" in completed.stdout
    assert "--end" in completed.stdout
    assert "--capital" in completed.stdout


@pytest.mark.backtest
def test_runner_does_not_construct_network_provider() -> None:
    text = Path("app/backtest/runner.py").read_text(encoding="utf-8")
    assert "OfflineMarketDataProvider" in text
    assert "create_market_data_provider" not in text
    assert "yfinance" not in text
