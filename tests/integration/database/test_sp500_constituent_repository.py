from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.universe.factory import create_universe_provider
from app.universe.service import UniverseService
from tests.fixtures.universe import membership, survivorship_memberships


@pytest.mark.integration
def test_upsert_memberships_is_idempotent(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    rows = survivorship_memberships()
    inserted, existing = repository.upsert_memberships(rows)
    assert inserted == 5
    assert existing == 0
    inserted_again, existing_again = repository.upsert_memberships(rows)
    assert inserted_again == 0
    assert existing_again == 5
    assert len(repository.get_all_memberships()) == 5


@pytest.mark.integration
def test_get_memberships_as_of_point_in_time(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    repository.upsert_memberships(survivorship_memberships())
    service = UniverseService(repository)
    assert service.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]
    assert service.get_symbols(date(2020, 1, 2)) == ["AAA", "CCC", "DDD"]
    assert service.get_symbols(date(2025, 1, 2)) == ["AAA", "DDD", "EEE"]


@pytest.mark.integration
def test_open_ended_membership_included(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    repository.upsert_memberships([membership("AAA", date(2010, 1, 1), None)])
    symbols = [item.symbol for item in repository.get_memberships_as_of(date(2026, 1, 1))]
    assert symbols == ["AAA"]


@pytest.mark.integration
def test_get_memberships_for_symbol_preserves_separate_periods(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    rows = (
        membership("XYZ", date(2010, 1, 1), date(2015, 6, 1)),
        membership("XYZ", date(2018, 3, 1), date(2020, 1, 1)),
    )
    repository.upsert_memberships(rows)
    loaded = repository.get_memberships("xyz")
    assert len(loaded) == 2
    assert loaded[0].end_date == date(2015, 6, 1)
    assert loaded[1].start_date == date(2018, 3, 1)


@pytest.mark.integration
def test_current_universe_ignores_as_of(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    repository.upsert_memberships(survivorship_memberships())
    provider = create_universe_provider("current", repository)
    assert provider.get_symbols(date(2015, 1, 2)) == ["AAA", "DDD", "EEE"]
    historical = create_universe_provider("historical_sp500", repository)
    assert historical.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]


@pytest.mark.integration
def test_boundary_excluded_on_end_date(db_session: Session) -> None:
    repository = PostgresSP500ConstituentRepository(db_session)
    repository.upsert_memberships(
        [membership("AAA", date(2015, 1, 1), date(2020, 1, 1))]
    )
    included = [item.symbol for item in repository.get_memberships_as_of(date(2015, 1, 1))]
    excluded = [item.symbol for item in repository.get_memberships_as_of(date(2020, 1, 1))]
    assert included == ["AAA"]
    assert excluded == []
