from datetime import date

import pytest

from app.universe.validation import intervals_overlap, validate_memberships
from tests.fixtures.universe import membership


@pytest.mark.unit
def test_duplicate_intervals() -> None:
    first = membership("AAA", date(2010, 1, 1), date(2015, 1, 1))
    duplicate = membership("AAA", date(2010, 1, 1), date(2015, 1, 1))
    report = validate_memberships([first, duplicate])
    assert len(report.valid) == 1
    assert len(report.duplicates) == 1
    assert report.has_blocking_errors is False


@pytest.mark.unit
def test_overlapping_intervals() -> None:
    left = membership("AAA", date(2010, 1, 1), date(2016, 1, 1))
    right = membership("AAA", date(2015, 1, 1), date(2020, 1, 1))
    report = validate_memberships([left, right])
    assert report.has_blocking_errors is True
    assert len(report.overlapping) >= 2


@pytest.mark.unit
def test_adjacent_intervals_do_not_overlap() -> None:
    left = membership("AAA", date(2010, 1, 1), date(2015, 1, 1))
    right = membership("AAA", date(2015, 1, 1), date(2020, 1, 1))
    assert intervals_overlap(left, right) is False
    report = validate_memberships([left, right])
    assert report.overlapping == ()
    assert len(report.valid) == 2


@pytest.mark.unit
def test_open_ended_overlap() -> None:
    open_ended = membership("AAA", date(2010, 1, 1), None)
    later = membership("AAA", date(2018, 1, 1), date(2020, 1, 1))
    assert intervals_overlap(open_ended, later) is True
