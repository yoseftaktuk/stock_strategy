from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.domain.models.market_bar import MarketBar
from app.strategy.config import MomentumConfig

UTC = timezone.utc
SERIES_START = date(2024, 1, 2)

TEST_CONFIG = MomentumConfig(
    lookback_days=5,
    skip_days=1,
    top_n=10,
    min_price=Decimal("10"),
    liquidity_window_days=2,
    min_dollar_volume=Decimal("1000"),
)


def make_bar(
    symbol: str,
    session: date,
    *,
    close: Decimal = Decimal("50"),
    open: Decimal | None = None,
    adjusted_close: Decimal | None = None,
    volume: int = 2_000_000,
    missing_adjusted_close: bool = False,
) -> MarketBar:
    adj: Decimal | None
    if missing_adjusted_close:
        adj = None
    elif adjusted_close is None:
        adj = close
    else:
        adj = adjusted_close
    session_open = close if open is None else open
    high = session_open if session_open >= close else close
    low = session_open if session_open <= close else close
    return MarketBar(
        symbol=symbol,
        timestamp=datetime(session.year, session.month, session.day, 16, 0, tzinfo=UTC),
        open=session_open,
        high=high,
        low=low,
        close=close,
        adjusted_close=adj,
        volume=volume,
    )


def make_series(
    symbol: str,
    count: int,
    *,
    start: date = SERIES_START,
    close: Decimal = Decimal("50"),
    adjusted_close: Decimal | None = None,
    volume: int = 2_000_000,
    adjusted_closes: Sequence[Decimal | None] | None = None,
    closes: Sequence[Decimal] | None = None,
    volumes: Sequence[int] | None = None,
    missing_adjusted_close: bool = False,
    open: Decimal | None = None,
    opens: Sequence[Decimal] | None = None,
) -> list[MarketBar]:
    bars: list[MarketBar] = []
    for index in range(count):
        session = start + timedelta(days=index)
        bar_close = closes[index] if closes is not None else close
        bar_open = opens[index] if opens is not None else open
        if adjusted_closes is not None:
            bar_adj = adjusted_closes[index]
            bars.append(
                make_bar(
                    symbol,
                    session,
                    close=bar_close,
                    open=bar_open,
                    adjusted_close=bar_adj,
                    volume=volumes[index] if volumes is not None else volume,
                    missing_adjusted_close=bar_adj is None,
                )
            )
        else:
            bars.append(
                make_bar(
                    symbol,
                    session,
                    close=bar_close,
                    open=bar_open,
                    adjusted_close=adjusted_close,
                    volume=volumes[index] if volumes is not None else volume,
                    missing_adjusted_close=missing_adjusted_close,
                )
            )
    return bars


def make_momentum_series(
    symbol: str,
    *,
    lookback_days: int,
    skip_days: int,
    lookback_price: Decimal,
    skip_price: Decimal,
    close: Decimal = Decimal("50"),
    volume: int = 2_000_000,
    extra_future_bars: int = 0,
    future_price: Decimal = Decimal("999"),
) -> list[MarketBar]:
    history_count = lookback_days + 1
    adjusted = [close] * history_count
    adjusted[-(lookback_days + 1)] = lookback_price
    adjusted[-(skip_days + 1)] = skip_price
    bars = make_series(
        symbol,
        history_count,
        close=close,
        volume=volume,
        adjusted_closes=adjusted,
    )
    if extra_future_bars:
        future_start = SERIES_START + timedelta(days=history_count)
        bars.extend(
            make_series(
                symbol,
                extra_future_bars,
                start=future_start,
                close=future_price,
                adjusted_close=future_price,
                volume=volume,
            )
        )
    return bars


def history_as_of(lookback_days: int) -> date:
    return SERIES_START + timedelta(days=lookback_days)


def universe_market_data(
    *,
    extra_future_bars: int = 0,
) -> dict[str, list[MarketBar]]:
    """Five symbols with distinct positive 12-1 momentum values."""
    specs: dict[str, tuple[Decimal, Decimal]] = {
        "NVDA": (Decimal("100"), Decimal("180")),
        "PLTR": (Decimal("100"), Decimal("174")),
        "MSFT": (Decimal("100"), Decimal("150")),
        "AAPL": (Decimal("100"), Decimal("120")),
        "AMD": (Decimal("100"), Decimal("110")),
    }
    return {
        symbol: make_momentum_series(
            symbol,
            lookback_days=TEST_CONFIG.lookback_days,
            skip_days=TEST_CONFIG.skip_days,
            lookback_price=lookback_price,
            skip_price=skip_price,
            extra_future_bars=extra_future_bars,
        )
        for symbol, (lookback_price, skip_price) in specs.items()
    }
