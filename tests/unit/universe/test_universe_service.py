from datetime import date

import pytest

from app.universe.exceptions import UniverseValidationError
from app.universe.memory import InMemoryUniverseProvider
from app.universe.service import UniverseService
from tests.fixtures.universe import membership, survivorship_memberships


class FakeRepository:
    def __init__(self) -> None:
        self.rows: list = []

    def get_memberships(self, symbol: str) -> list:
        return [item for item in self.rows if item.symbol == symbol.upper()]

    def get_memberships_as_of(self, as_of: date) -> list:
        return [item for item in self.rows if item.contains(as_of)]

    def get_all_memberships(self) -> list:
        return list(self.rows)

    def upsert_memberships(self, memberships: list) -> tuple[int, int]:
        self.rows.extend(memberships)
        return len(memberships), 0
    def __init__(self) -> None:
        self.rows: list = []

    def get_memberships(self, symbol: str) -> list:
        return [item for item in self.rows if item.symbol == symbol.upper()]

    def get_memberships_as_of(self, as_of: date) -> list:
        return [item for item in self.rows if item.contains(as_of)]

    def get_all_memberships(self) -> list:
        return list(self.rows)

    def upsert_memberships(self, memberships: list) -> tuple[int, int]:
        self.rows.extend(memberships)
        return len(memberships), 0


@pytest.mark.unit
def test_service_get_symbols_uses_provider() -> None:
    repository = FakeRepository()
    repository.rows.extend(survivorship_memberships())
    service = UniverseService(repository, provider=InMemoryUniverseProvider(repository.rows))
    assert service.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]


@pytest.mark.unit
def test_persist_overlapping_does_not_write() -> None:
    repository = FakeRepository()
    service = UniverseService(repository)
    with pytest.raises(UniverseValidationError, match="Overlapping"):
        service.persist_memberships(
            [
                membership("AAA", date(2010, 1, 1), date(2016, 1, 1)),
                membership("AAA", date(2015, 1, 1), date(2020, 1, 1)),
            ],
            source="test",
            source_version="v1",
            raw_records=2,
        )
    assert repository.rows == []


@pytest.mark.unit
def test_persist_duplicates_are_counted_and_unique_rows_saved() -> None:
    repository = FakeRepository()
    service = UniverseService(repository)
    first = membership("AAA", date(2010, 1, 1), date(2015, 1, 1))
    summary = service.persist_memberships(
        [first, first],
        source="test",
        source_version="v1",
        raw_records=1,
    )
    assert summary.duplicate_intervals == 1
    assert summary.inserted == 1
    assert summary.ok
    assert len(repository.rows) == 1


@pytest.mark.unit
def test_symbols_overlapping_window_is_union_not_current_members() -> None:
    repository = FakeRepository()
    repository.rows.extend(
        [
            membership("AAA", date(2010, 1, 1), date(2016, 1, 1)),
            membership("BBB", date(2020, 1, 1), None),
            membership("CCC", date(2010, 1, 1), None),
        ]
    )
    service = UniverseService(repository)
    assert service.get_symbols(date(2025, 1, 2)) == ["BBB", "CCC"]
    assert service.symbols_overlapping_window(date(2015, 1, 1), date(2025, 12, 31)) == [
        "AAA",
        "BBB",
        "CCC",
    ]
