"""Application-facing Security Master orchestration.

The service does not guess identities. Source catalogs produce validated
intervals; the repository persists them; the in-memory catalog answers
ticker+date resolution.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.database.repositories.interfaces import SecurityMasterRepository
from app.domain.models.security import (
    SCHEME_YAHOO,
    Resolution,
    Security,
    SecurityIdentifier,
    SecurityTicker,
)
from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.exceptions import SecurityMasterValidationError
from app.security_master.validation import validate_tickers


@dataclass(frozen=True)
class SecurityMasterImportSummary:
    source: str
    source_version: str
    securities: int
    tickers: int
    identifiers: int
    inserted_securities: int
    existing_securities: int
    inserted_tickers: int
    existing_tickers: int
    inserted_identifiers: int
    existing_identifiers: int

    def format(self) -> str:
        return "\n".join(
            [
                "Security Master Import",
                f"Source: {self.source}",
                f"Source version: {self.source_version}",
                f"Securities: {self.securities} (inserted {self.inserted_securities}, existing {self.existing_securities})",
                f"Tickers: {self.tickers} (inserted {self.inserted_tickers}, existing {self.existing_tickers})",
                f"Identifiers: {self.identifiers} (inserted {self.inserted_identifiers}, existing {self.existing_identifiers})",
            ]
        )


class SecurityMasterService:
    def __init__(
        self,
        repository: SecurityMasterRepository,
        catalog: InMemorySecurityMaster | None = None,
    ) -> None:
        self._repository = repository
        self._catalog = catalog

    def resolve_security(self, ticker: str, as_of: date) -> Resolution:
        return self._require_catalog().resolve_security(ticker, as_of)

    def resolve_market_data_symbol(
        self,
        symbol: str,
        as_of: date,
        source: str = SCHEME_YAHOO,
    ) -> Resolution:
        return self._require_catalog().resolve_market_data_symbol(symbol, as_of, source)

    def get_ticker_history(self, seed_key: str) -> Sequence[SecurityTicker]:
        return self._require_catalog().get_ticker_history(seed_key)

    def get_security(self, seed_key: str) -> Security | None:
        return self._require_catalog().get_security(seed_key)

    def has_vendor_mapping(self, symbol: str, source: str = SCHEME_YAHOO) -> bool:
        return self._require_catalog().has_vendor_mapping(symbol, source)

    def tickers(self) -> Sequence[SecurityTicker]:
        return self._require_catalog().tickers()

    def load_catalog(self) -> InMemorySecurityMaster:
        securities, tickers, identifiers = self._repository.load_all()
        catalog = InMemorySecurityMaster(securities, tickers, identifiers)
        self._catalog = catalog
        return catalog

    def persist_catalog(
        self,
        catalog: InMemorySecurityMaster,
        *,
        source: str,
        source_version: str,
    ) -> SecurityMasterImportSummary:
        report = validate_tickers(catalog.tickers())
        if report.has_blocking_errors:
            details = tuple(issue.format() for issue in report.overlapping)
            raise SecurityMasterValidationError(
                "overlapping ticker intervals",
                issues=details,
            )
        inserted_s, existing_s = self._repository.upsert_securities(catalog.securities())
        inserted_t, existing_t = self._repository.upsert_tickers(catalog.tickers())
        inserted_i, existing_i = self._repository.upsert_identifiers(catalog.identifiers())
        self._catalog = catalog
        return SecurityMasterImportSummary(
            source=source,
            source_version=source_version,
            securities=len(catalog.securities()),
            tickers=len(catalog.tickers()),
            identifiers=len(catalog.identifiers()),
            inserted_securities=inserted_s,
            existing_securities=existing_s,
            inserted_tickers=inserted_t,
            existing_tickers=existing_t,
            inserted_identifiers=inserted_i,
            existing_identifiers=existing_i,
        )

    def _require_catalog(self) -> InMemorySecurityMaster:
        if self._catalog is None:
            return self.load_catalog()
        return self._catalog
