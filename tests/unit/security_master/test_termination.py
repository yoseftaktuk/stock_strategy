from datetime import date

import pytest

from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.models import Security, SecurityTicker
from app.security_master.seed import load_known_identities_catalog
from app.security_master.termination import is_known_listing_termination


def _master(*, status: str, valid_to: date | None) -> InMemorySecurityMaster:
    return InMemorySecurityMaster(
        [Security(seed_key="acme", display_name="Acme", status=status)],
        [
            SecurityTicker(
                seed_key="acme",
                scheme="listing",
                ticker="ACME",
                valid_from=date(2010, 1, 1),
                valid_to=valid_to,
            )
        ],
    )


@pytest.mark.unit
def test_unresolved_series_end_is_not_termination() -> None:
    assert (
        is_known_listing_termination(
            None,
            "GROW",
            last_bar=date(2024, 2, 10),
            session=date(2024, 2, 11),
        )
        is False
    )
    empty = InMemorySecurityMaster()
    assert (
        is_known_listing_termination(
            empty,
            "GROW",
            last_bar=date(2024, 2, 10),
            session=date(2024, 2, 11),
        )
        is False
    )


@pytest.mark.unit
def test_delisted_listing_is_known_termination() -> None:
    master = _master(status="DELISTED", valid_to=date(2018, 12, 21))
    assert (
        is_known_listing_termination(
            master,
            "ACME",
            last_bar=date(2018, 12, 20),
            session=date(2018, 12, 21),
        )
        is True
    )


@pytest.mark.unit
def test_last_bar_on_exclusive_end_still_terminates() -> None:
    master = _master(status="DELISTED", valid_to=date(2018, 12, 21))
    assert (
        is_known_listing_termination(
            master,
            "ACME",
            last_bar=date(2018, 12, 21),
            session=date(2018, 12, 24),
        )
        is True
    )


@pytest.mark.unit
def test_active_listing_end_is_not_termination() -> None:
    master = _master(status="ACTIVE", valid_to=date(2025, 1, 21))
    assert (
        is_known_listing_termination(
            master,
            "ACME",
            last_bar=date(2025, 1, 20),
            session=date(2025, 1, 21),
        )
        is False
    )


@pytest.mark.unit
def test_esrx_catalog_is_known_acquisition_termination() -> None:
    master = load_known_identities_catalog()
    assert (
        is_known_listing_termination(
            master,
            "ESRX",
            last_bar=date(2018, 12, 21),
            session=date(2018, 12, 24),
        )
        is True
    )
    assert (
        is_known_listing_termination(
            master,
            "ESRX",
            last_bar=date(2018, 12, 21),
            session=date(2018, 12, 21),
        )
        is False
    )
