from datetime import datetime


class DataProviderError(Exception):
    """Raised when a market-data source cannot be read."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.timestamp = timestamp
        self.source = source
        super().__init__(_format_message(message, symbol=symbol, timestamp=timestamp, source=source))


class DataValidationError(Exception):
    """Raised when market data fails fatal validation."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.timestamp = timestamp
        self.source = source
        super().__init__(_format_message(message, symbol=symbol, timestamp=timestamp, source=source))


class DataImportError(Exception):
    """Raised when a market-data import request or orchestration fails."""

    def __init__(
        self,
        message: str,
        *,
        symbol: str | None = None,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.timestamp = timestamp
        self.source = source
        super().__init__(_format_message(message, symbol=symbol, timestamp=timestamp, source=source))


def _format_message(
    message: str,
    *,
    symbol: str | None,
    timestamp: datetime | None,
    source: str | None,
) -> str:
    parts = [message]
    if symbol is not None:
        parts.append(f"symbol={symbol}")
    if timestamp is not None:
        parts.append(f"timestamp={timestamp.isoformat()}")
    if source is not None:
        parts.append(f"source={source}")
    return " ".join(parts)
