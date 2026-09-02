from datetime import date

import pytest

from app.domain.exceptions import DomainValidationError
from app.universe.memory import InMemoryUniverseProvider
from app.universe.models import ConstituentMembership
from tests.fixtures.universe import membership, survivorship_memberships


@pytest.mark.unit
def test_get_symbols_as_of_date() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    assert provider.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]
    assert provider.get_symbols(date(2020, 1, 2)) == ["AAA", "CCC", "DDD"]
    assert provider.get_symbols(date(2025, 1, 2)) == ["AAA", "DDD", "EEE"]


@pytest.mark.unit
def test_membership_before_start() -> None:
    item = membership("XYZ", date(2020, 1, 1), date(2021, 1, 1))
    assert item.contains(date(2019, 12, 31)) is False
    provider = InMemoryUniverseProvider([item])
    assert provider.get_symbols(date(2019, 12, 31)) == []


@pytest.mark.unit
def test_membership_during_period() -> None:
    item = membership("XYZ", date(2020, 1, 1), date(2021, 1, 1))
    assert item.contains(date(2020, 6, 15)) is True
    provider = InMemoryUniverseProvider([item])
    assert provider.get_symbols(date(2020, 6, 15)) == ["XYZ"]


@pytest.mark.unit
def test_membership_after_end() -> None:
    item = membership("XYZ", date(2020, 1, 1), date(2021, 1, 1))
    assert item.contains(date(2021, 1, 1)) is False
    assert item.contains(date(2022, 1, 1)) is False
    provider = InMemoryUniverseProvider([item])
    assert provider.get_symbols(date(2021, 1, 1)) == []


@pytest.mark.unit
def test_multiple_membership_periods() -> None:
    periods = (
        membership("XYZ", date(2010, 1, 1), date(2015, 6, 1)),
        membership("XYZ", date(2018, 3, 1), date(2020, 1, 1)),
    )
    provider = InMemoryUniverseProvider(periods)
    assert provider.get_symbols(date(2012, 1, 1)) == ["XYZ"]
    assert provider.get_symbols(date(2016, 1, 1)) == []
    assert provider.get_symbols(date(2019, 1, 1)) == ["XYZ"]
    assert provider.get_symbols(date(2020, 1, 1)) == []


@pytest.mark.unit
def test_deterministic_ordering() -> None:
    provider = InMemoryUniverseProvider(
        (
            membership("CCC", date(2010, 1, 1)),
            membership("AAA", date(2010, 1, 1)),
            membership("BBB", date(2010, 1, 1)),
            membership("AAA", date(2010, 1, 1)),
        )
    )
    assert provider.get_symbols(date(2015, 1, 2)) == ["AAA", "BBB", "CCC"]


@pytest.mark.unit
def test_boundary_dates() -> None:
    item = membership("AAA", date(2015, 1, 1), date(2020, 1, 1))
    assert item.contains(date(2015, 1, 1)) is True
    assert item.contains(date(2019, 12, 31)) is True
    assert item.contains(date(2020, 1, 1)) is False
    provider = InMemoryUniverseProvider([item])
    assert provider.get_symbols(date(2015, 1, 1)) == ["AAA"]
    assert provider.get_symbols(date(2020, 1, 1)) == []


@pytest.mark.unit
def test_future_membership_does_not_change_past_universe() -> None:
    provider = InMemoryUniverseProvider(
        (
            membership("AAA", date(2010, 1, 1)),
            membership("XYZ", date(2020, 1, 1)),
        )
    )
    past = provider.get_symbols(date(2018, 1, 1))
    assert "XYZ" not in past
    assert past == ["AAA"]
    assert provider.get_symbols(date(2020, 1, 1)) == ["AAA", "XYZ"]


@pytest.mark.unit
def test_removed_constituent_can_be_selected_during_valid_period() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    assert "BBB" in provider.get_symbols(date(2015, 6, 1))
    assert "BBB" not in provider.get_symbols(date(2025, 1, 2))


@pytest.mark.unit
def test_survivorship_fixture_excludes_future_and_removed_names() -> None:
    provider = InMemoryUniverseProvider(survivorship_memberships())
    as_2015 = provider.get_symbols(date(2015, 1, 2))
    as_2025 = provider.get_symbols(date(2025, 1, 2))
    assert "DDD" not in as_2015
    assert "EEE" not in as_2015
    assert "BBB" not in as_2025


@pytest.mark.unit
def test_membership_rejects_invalid_interval() -> None:
    with pytest.raises(DomainValidationError, match="start_date must be earlier"):
        ConstituentMembership(symbol="AAA", start_date=date(2020, 1, 1), end_date=date(2020, 1, 1))
