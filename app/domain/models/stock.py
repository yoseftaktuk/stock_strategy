from dataclasses import dataclass

from app.domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Stock:
    symbol: str
    exchange: str
    currency: str

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise DomainValidationError("symbol must not be empty")
        if not self.exchange.strip():
            raise DomainValidationError("exchange must not be empty")
        if not self.currency.strip():
            raise DomainValidationError("currency must not be empty")
        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "currency", self.currency.strip().upper())
