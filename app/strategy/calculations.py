from collections.abc import Sequence
from decimal import Decimal

from app.domain.models.market_bar import MarketBar
from app.strategy.exceptions import StrategyDataError


def calculate_momentum(
    bars: Sequence[MarketBar],
    lookback_days: int,
    skip_days: int,
) -> Decimal:
    """Return 12-1 style momentum: Price[t-skip] / Price[t-lookback] - 1.

    Uses adjusted_close only. Does not mutate ``bars``. Incoming data need not
    be sorted; a copy is sorted by timestamp ascending before indexing.
    """
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    minimum = lookback_days + 1
    if len(ordered) < minimum:
        raise StrategyDataError(
            f"insufficient history: need {minimum} bars, got {len(ordered)}"
        )

    skip_bar = ordered[-(skip_days + 1)]
    lookback_bar = ordered[-(lookback_days + 1)]

    skip_price = _require_adjusted_close(skip_bar)
    lookback_price = _require_adjusted_close(lookback_bar)
    if lookback_price == 0:
        raise StrategyDataError(
            f"lookback adjusted_close is zero symbol={lookback_bar.symbol}"
        )

    return skip_price / lookback_price - 1


def calculate_average_dollar_volume(
    bars: Sequence[MarketBar],
    window_days: int,
) -> Decimal:
    """Return mean(close * volume) over the last ``window_days`` bars.

    Does not mutate ``bars``. Incoming data need not be sorted.
    """
    if window_days <= 0:
        raise StrategyDataError("window_days must be > 0")

    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    if len(ordered) < window_days:
        raise StrategyDataError(
            f"insufficient history for dollar volume: need {window_days} bars, "
            f"got {len(ordered)}"
        )

    window = ordered[-window_days:]
    total = sum((bar.close * bar.volume for bar in window), Decimal("0"))
    return total / Decimal(window_days)


def _require_adjusted_close(bar: MarketBar) -> Decimal:
    if bar.adjusted_close is None:
        raise StrategyDataError(
            f"adjusted_close is unavailable symbol={bar.symbol} "
            f"timestamp={bar.timestamp.isoformat()}"
        )
    return bar.adjusted_close
