"""Market-data price-quality assessment.

PIT membership and price usability are independent. A series can fail quality
without being removed from the universe. Callers must not use ticker blacklists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.models.market_bar import MarketBar

DEFAULT_EXTREME_FIRST_CLOSE = Decimal("1000")
REASON_EXTREME_FIRST_CLOSE = "extreme_first_close"


@dataclass(frozen=True)
class PriceSeriesQuality:
    symbol: str
    usable: bool
    reason: str | None = None


def assess_price_series(
    bars: Sequence[MarketBar],
    *,
    extreme_first_close: Decimal = DEFAULT_EXTREME_FIRST_CLOSE,
) -> PriceSeriesQuality:
    """Classify a loaded price series as usable or unusable.

    Empty series are not unusable; they are missing and belong in coverage.
    """
    if not bars:
        return PriceSeriesQuality(symbol="", usable=True, reason=None)
    symbol = bars[0].symbol
    first = min(bars, key=lambda bar: bar.timestamp)
    if first.close >= extreme_first_close:
        return PriceSeriesQuality(
            symbol=symbol,
            usable=False,
            reason=REASON_EXTREME_FIRST_CLOSE,
        )
    return PriceSeriesQuality(symbol=symbol, usable=True, reason=None)


def unusable_symbols(
    market_data: Mapping[str, Sequence[MarketBar]],
    *,
    extreme_first_close: Decimal = DEFAULT_EXTREME_FIRST_CLOSE,
) -> dict[str, str]:
    """Return symbol → reason for loaded series that fail price-quality checks."""
    flagged: dict[str, str] = {}
    for symbol, bars in market_data.items():
        if not bars:
            continue
        assessment = assess_price_series(bars, extreme_first_close=extreme_first_close)
        if not assessment.usable and assessment.reason is not None:
            flagged[symbol] = assessment.reason
    return flagged
