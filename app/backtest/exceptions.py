from collections.abc import Mapping
from datetime import date


class BacktestConfigError(ValueError):
    """Raised when backtest configuration fails validation."""


class EmptyUniverseError(ValueError):
    """Raised when no symbols are available for a backtest."""


class InsufficientHistoryError(ValueError):
    """Raised when loaded bars cannot satisfy the momentum lookback warmup."""

    def __init__(
        self,
        *,
        need: int,
        loaded: int,
        lookback_days: int,
        bar_counts: Mapping[str, int],
        start: date,
        end: date,
        csv_data_path: str,
    ) -> None:
        self.need = need
        self.loaded = loaded
        self.lookback_days = lookback_days
        self.bar_counts = dict(bar_counts)
        self.start = start
        self.end = end
        self.csv_data_path = csv_data_path
        counts = ", ".join(f"{symbol}={count}" for symbol, count in self.bar_counts.items()) or "none"
        super().__init__(
            "Not enough history to run the momentum backtest. "
            f"Need at least {need} daily bars (lookback {lookback_days} + 1 warmup); "
            f"loaded {loaded} ({counts}). "
            f"Requested {start.isoformat()} → {end.isoformat()}. "
            f"Add a longer daily CSV under {csv_data_path} and import it with: "
            "python scripts/import_market_data.py --symbol AAPL --start YYYY-MM-DD --end YYYY-MM-DD"
        )
