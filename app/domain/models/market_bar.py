from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class MarketBar:
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
