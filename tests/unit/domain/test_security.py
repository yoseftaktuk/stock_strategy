from datetime import date

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.security import (
    RESOLUTION_UNRESOLVED,
    Resolution,
    Security,
    SecurityTicker,
)


@pytest.mark.unit
def test_security_normalizes_fields() -> None:
    security = Security(seed_key=" block-inc-class-a ", display_name=" Block, Inc. ", currency="usd")
    assert security.seed_key == "block-inc-class-a"
    assert security.display_name == "Block, Inc."
    assert security.currency == "USD"


@pytest.mark.unit
def test_security_empty_seed_key_raises() -> None:
    with pytest.raises(DomainValidationError, match="seed_key must not be empty"):
        Security(seed_key="  ", display_name="X")


@pytest.mark.unit
def test_ticker_interval_is_half_open() -> None:
    ticker = SecurityTicker(
        seed_key="spectra-energy",
        scheme="listing",
        ticker="se",
        valid_from=date(2007, 1, 3),
        valid_to=date(2017, 2, 27),
    )
    assert ticker.ticker == "SE"
    assert ticker.contains(date(2007, 1, 3))
    assert ticker.contains(date(2017, 2, 26))
    assert not ticker.contains(date(2017, 2, 27))
    assert not ticker.contains(date(2007, 1, 2))


@pytest.mark.unit
def test_invalid_ticker_interval_raises() -> None:
    with pytest.raises(DomainValidationError, match="valid_from must be earlier than valid_to"):
        SecurityTicker(
            seed_key="x",
            scheme="listing",
            ticker="X",
            valid_from=date(2020, 1, 1),
            valid_to=date(2020, 1, 1),
        )


@pytest.mark.unit
def test_unresolved_must_not_carry_a_security() -> None:
    with pytest.raises(DomainValidationError, match="UNRESOLVED"):
        Resolution(
            status=RESOLUTION_UNRESOLVED,
            security=Security(seed_key="x", display_name="X"),
        )
    assert Resolution.unresolved().is_resolved is False
