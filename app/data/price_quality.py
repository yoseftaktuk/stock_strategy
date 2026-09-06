"""Market-data price-quality assessment.

PIT membership and price usability are independent. A series can fail quality
without being removed from the universe. Callers must not use ticker blacklists.

High traded prices are valid (AZO / MTD / NVR class). Identity mismatch and
OHLC invariant failures are checked elsewhere; this module does not treat a
large first close as corrupted data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.models.market_bar import MarketBar


@dataclass(frozen=True)
class PriceSeriesQuality:
    symbol: str
    usable: bool
    reason: str | None = None


def assess_price_series(bars: Sequence[MarketBar]) -> PriceSeriesQuality:
    """Classify a loaded price series as usable or unusable.

    Empty series are not unusable; they are missing and belong in coverage.
    OHLC sanity is enforced when bars are constructed. Identity is separate.
    """
    if not bars:
        return PriceSeriesQuality(symbol="", usable=True, reason=None)
    return PriceSeriesQuality(symbol=bars[0].symbol, usable=True, reason=None)


def unusable_symbols(
    market_data: Mapping[str, Sequence[MarketBar]],
) -> dict[str, str]:
    """Return symbol → reason for loaded series that fail price-quality checks."""
    flagged: dict[str, str] = {}
    for symbol, bars in market_data.items():
        if not bars:
            continue
        assessment = assess_price_series(bars)
        if not assessment.usable and assessment.reason is not None:
            flagged[symbol] = assessment.reason
    return flagged
