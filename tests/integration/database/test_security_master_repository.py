from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.database.repositories.security_master import PostgresSecurityMasterRepository
from app.security_master.seed import load_known_identities_catalog
from app.security_master.service import SecurityMasterService


@pytest.mark.integration
def test_persist_known_identities_is_idempotent(db_session: Session) -> None:
    catalog = load_known_identities_catalog()
    repository = PostgresSecurityMasterRepository(db_session)
    service = SecurityMasterService(repository)
    first = service.persist_catalog(catalog, source="test", source_version="1")
    assert first.inserted_securities == len(catalog.securities())
    assert first.inserted_tickers == len(catalog.tickers())
    second = service.persist_catalog(catalog, source="test", source_version="1")
    assert second.inserted_securities == 0
    assert second.existing_securities == len(catalog.securities())
    assert second.inserted_tickers == 0


@pytest.mark.integration
def test_loaded_catalog_resolves_known_cases(db_session: Session) -> None:
    catalog = load_known_identities_catalog()
    repository = PostgresSecurityMasterRepository(db_session)
    service = SecurityMasterService(repository)
    service.persist_catalog(catalog, source="test", source_version="1")
    loaded = service.load_catalog()

    spectra = loaded.resolve_security("SE", date(2015, 6, 1))
    sea = loaded.resolve_security("SE", date(2018, 6, 1))
    assert spectra.security is not None and sea.security is not None
    assert spectra.security.seed_key == "spectra-energy"
    assert sea.security.seed_key == "sea-limited"
    assert spectra.security.security_id != sea.security.security_id

    sq = loaded.resolve_security("SQ", date(2020, 1, 2))
    xyz = loaded.resolve_security("XYZ", date(2025, 6, 1))
    assert sq.security is not None and xyz.security is not None
    assert sq.security.security_id == xyz.security.security_id

    unknown = loaded.resolve_security("MSFT", date(2020, 1, 2))
    assert unknown.is_resolved is False

    har = loaded.resolve_security("HAR", date(2015, 6, 1))
    assert har.security is not None
    assert loaded.resolve_market_data_symbol("HAR", date(2015, 6, 1)).is_resolved is False
