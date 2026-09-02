"""In-memory Security Master catalog.

Unknown ticker+date pairs return UNRESOLVED. The catalog never invents a
security from a ticker string.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from app.data.validation import normalize_symbol
from app.domain.models.security import (
    SCHEME_LISTING,
    SCHEME_YAHOO,
    Resolution,
    Security,
    SecurityIdentifier,
    SecurityTicker,
)
from app.security_master.exceptions import SecurityMasterValidationError
from app.security_master.validation import validate_tickers


class InMemorySecurityMaster:
    """Resolve ticker+date against an in-memory evidence catalog."""

    def __init__(
        self,
        securities: Sequence[Security] = (),
        tickers: Sequence[SecurityTicker] = (),
        identifiers: Sequence[SecurityIdentifier] = (),
    ) -> None:
        report = validate_tickers(tickers)
        if report.has_blocking_errors:
            details = tuple(issue.format() for issue in report.overlapping)
            raise SecurityMasterValidationError(
                "overlapping ticker intervals",
                issues=details,
            )
        by_key = {item.seed_key: item for item in securities}
        missing = sorted(
            {
                ticker.seed_key
                for ticker in report.valid
                if ticker.seed_key not in by_key
            }
            | {
                identifier.seed_key
                for identifier in identifiers
                if identifier.seed_key not in by_key
            }
        )
        if missing:
            raise SecurityMasterValidationError(
                "ticker or identifier seed_key has no security",
                issues=tuple(missing),
            )
        self._securities = by_key
        self._tickers = report.valid
        self._identifiers = tuple(identifiers)
        grouped: dict[tuple[str, str], list[SecurityTicker]] = defaultdict(list)
        for ticker in report.valid:
            grouped[(ticker.scheme, ticker.ticker)].append(ticker)
        self._by_scheme_ticker = {
            key: tuple(sorted(values, key=lambda item: item.valid_from))
            for key, values in grouped.items()
        }

    def resolve_security(self, ticker: str, as_of: date) -> Resolution:
        return self._resolve(SCHEME_LISTING, ticker, as_of)

    def resolve_market_data_symbol(
        self,
        symbol: str,
        as_of: date,
        source: str = SCHEME_YAHOO,
    ) -> Resolution:
        return self._resolve(source, symbol, as_of)

    def get_ticker_history(self, seed_key: str) -> tuple[SecurityTicker, ...]:
        return tuple(
            ticker
            for ticker in self._tickers
            if ticker.seed_key == seed_key and ticker.scheme == SCHEME_LISTING
        )

    def get_security(self, seed_key: str) -> Security | None:
        return self._securities.get(seed_key)

    def securities(self) -> tuple[Security, ...]:
        return tuple(self._securities[key] for key in sorted(self._securities))

    def tickers(self) -> tuple[SecurityTicker, ...]:
        return self._tickers

    def identifiers(self) -> tuple[SecurityIdentifier, ...]:
        return self._identifiers

    def has_vendor_mapping(self, symbol: str, source: str = SCHEME_YAHOO) -> bool:
        normalized = normalize_symbol(symbol)
        if not normalized:
            return False
        return (source.strip().lower(), normalized) in self._by_scheme_ticker

    def listing_seed_keys(self, ticker: str, start: date, end: date) -> tuple[str, ...]:
        """Seed keys whose listing ticker overlaps ``[start, end]`` (inclusive)."""
        normalized = normalize_symbol(ticker)
        if not normalized:
            return ()
        keys: list[str] = []
        seen: set[str] = set()
        for item in self._by_scheme_ticker.get((SCHEME_LISTING, normalized), ()):
            if item.valid_from > end:
                continue
            if item.valid_to is not None and start >= item.valid_to:
                continue
            if item.seed_key not in seen:
                seen.add(item.seed_key)
                keys.append(item.seed_key)
        return tuple(keys)

    def _resolve(self, scheme: str, ticker: str, as_of: date) -> Resolution:
        normalized = normalize_symbol(ticker)
        if not normalized:
            return Resolution.unresolved()
        scheme_key = scheme.strip().lower()
        matches = [
            item
            for item in self._by_scheme_ticker.get((scheme_key, normalized), ())
            if item.contains(as_of)
        ]
        if len(matches) != 1:
            return Resolution.unresolved()
        security = self._securities.get(matches[0].seed_key)
        if security is None:
            return Resolution.unresolved()
        return Resolution.resolved(security)
