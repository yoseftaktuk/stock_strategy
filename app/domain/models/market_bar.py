from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class MarketBar:
    """One daily bar. Field names are vendor columns, not accounting roles.

    On the current Yahoo path (``auto_adjust=False``):

    * ``open`` / ``high`` / ``low`` / ``close`` are Yahoo OHLC. Empirically
      these are **split-adjusted**, not raw unadjusted prints. They are not
      dividend-adjusted. Do not treat ``close`` as economic unadjusted close.
    * ``adjusted_close`` is Yahoo Adj Close (split **and** dividend adjusted).
      Momentum/signal only. Never execution, mark-to-market, or termination.

    There is no dividend, split, or merger field on this type.
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: int

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise DomainValidationError("symbol must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.tzinfo.utcoffset(self.timestamp) is None:
            raise DomainValidationError("timestamp must be timezone-aware")

        prices = (self.open, self.high, self.low, self.close)
        if self.adjusted_close is not None:
            prices = (*prices, self.adjusted_close)

        for name, value in zip(
            ("open", "high", "low", "close", "adjusted_close"),
            prices,
            strict=False,
        ):
            if value < 0:
                raise DomainValidationError(f"{name} must be non-negative")

        if self.high < self.low:
            raise DomainValidationError("high must be >= low")
        if self.high < self.open:
            raise DomainValidationError("high must be >= open")
        if self.high < self.close:
            raise DomainValidationError("high must be >= close")
        if self.low > self.open:
            raise DomainValidationError("low must be <= open")
        if self.low > self.close:
            raise DomainValidationError("low must be <= close")
        if self.volume < 0:
            raise DomainValidationError("volume must be non-negative")
