from datetime import date

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.listing import Listing
from app.security_master.exceptions import SecurityMasterValidationError
from app.security_master.identity_resolver import CatalogIdentityResolver
from app.security_master.seed import load_known_identities_catalog


@pytest.mark.unit
def test_yahoo_vendor_row_is_not_a_listing() -> None:
    resolver = CatalogIdentityResolver.from_catalog(load_known_identities_catalog())
    before_listing = resolver.resolve("XYZ", date(2016, 1, 4))
    after_listing = resolver.resolve("XYZ", date(2025, 6, 1))
    assert before_listing.is_resolved is False
    assert before_listing.security_id is None
    assert after_listing.is_resolved is True
    assert after_listing.ticker_as_of == "XYZ"


@pytest.mark.unit
def test_empty_ticker_is_rejected() -> None:
    resolver = CatalogIdentityResolver()
    with pytest.raises(DomainValidationError, match="ticker must not be empty"):
        resolver.resolve("  ", date(2020, 1, 2))


@pytest.mark.unit
def test_pit_occupancy_is_used_when_catalog_has_no_listing() -> None:
    resolver = CatalogIdentityResolver()
    first = resolver.resolve(
        "SE",
        date(2015, 6, 1),
        occupancy_from=date(2007, 1, 3),
        occupancy_to=date(2017, 2, 27),
    )
    second = resolver.resolve(
        "SE",
        date(2018, 6, 1),
        occupancy_from=date(2017, 10, 20),
    )
    assert first.security_id is None and second.security_id is None
    assert first.listing.listing_id != second.listing.listing_id
@pytest.mark.unit
def test_overlapping_unresolved_occupancies_are_rejected() -> None:
    with pytest.raises(SecurityMasterValidationError, match="overlapping listing occupancies"):
        CatalogIdentityResolver(
            listings=(
                Listing(ticker="SE", valid_from=date(2010, 1, 1), valid_to=date(2020, 1, 1)),
                Listing(ticker="SE", valid_from=date(2015, 1, 1), valid_to=date(2025, 1, 1)),
            )
        )
