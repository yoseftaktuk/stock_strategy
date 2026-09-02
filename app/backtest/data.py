from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path

from app.data.market_data import MarketDataService
from app.domain.models.market_bar import MarketBar

_OHLCV_COLUMNS = frozenset({"symbol", "timestamp", "open", "high", "low", "close", "volume"})
_UNIVERSE_CACHE_STEMS = frozenset({"sp500_historical"})


def discover_csv_symbols(data_dir: Path) -> tuple[str, ...]:
    """Return symbols implied by price CSVs in ``data_dir``.

    Universe cache files (membership snapshots) are not tickers and are skipped.
    """
    if not data_dir.is_dir():
        return ()
    symbols: list[str] = []
    seen: set[str] = set()
    for path in sorted(data_dir.glob("*.csv")):
        if not _is_market_price_csv(path):
            continue
        stem = path.stem
        if stem.lower().endswith("_daily"):
            stem = stem[: -len("_daily")]
        symbol = stem.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return tuple(symbols)


def _is_market_price_csv(path: Path) -> bool:
    if path.stem.lower() in _UNIVERSE_CACHE_STEMS:
        return False
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            header = handle.readline()
    except OSError:
        return False
    columns = {part.strip().lower() for part in header.split(",")}
    return _OHLCV_COLUMNS <= columns


def max_bar_count(market_data: Mapping[str, Sequence[MarketBar]]) -> int:
    """Return the longest per-symbol bar series, or 0 when nothing was loaded."""
    return max((len(bars) for bars in market_data.values()), default=0)


def warmup_history_start(start: date, lookback_days: int) -> date:
    """Calendar day to begin loading so Momentum has lookback bars before ``start``.

    Matches the existing buffer: ``lookback_days * 2 + 40`` calendar days.
    For lookback 252 this is 544 calendar days (about 2013-07-06 for a 2015-01-01 start).
    """
    return start - timedelta(days=lookback_days * 2 + 40)


def load_market_data(
    service: MarketDataService,
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    lookback_days: int,
) -> dict[str, list[MarketBar]]:
    """Load history once, including a calendar buffer before ``start`` for warmup."""
    history_start = warmup_history_start(start, lookback_days)
    loaded: dict[str, list[MarketBar]] = {}
    for symbol in symbols:
        loaded[symbol] = list(service.get_history(symbol, history_start, end))
    return loaded
