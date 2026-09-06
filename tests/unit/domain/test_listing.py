from datetime import date

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.listing import (
    Listing,
    occupancy_listing_id,
    unknown_occupancy_listing_id,
)


@pytest.mark.unit
def test_listing_interval_is_half_open() -> None:
    listing = Listing(
        ticker="se",
        valid_from=date(2007, 1, 3),
        valid_to=date(2017, 2, 27),
    )
    assert listing.ticker == "SE"
    assert listing.contains(date(2007, 1, 3))
    assert listing.contains(date(2017, 2, 26))
    assert not listing.contains(date(2017, 2, 27))
    assert not listing.contains(date(2007, 1, 2))
    assert listing.occupancy_known is True


@pytest.mark.unit
def test_listing_id_is_occupancy_not_ticker() -> None:
    spectra = Listing(ticker="SE", valid_from=date(2007, 1, 3), valid_to=date(2017, 2, 27))
    sea = Listing(ticker="SE", valid_from=date(2017, 10, 20))
    assert spectra.listing_id != "SE"
    assert sea.listing_id != "SE"
    assert spectra.listing_id != sea.listing_id
    assert spectra.listing_id == occupancy_listing_id(
        ticker="SE",
        exchange=None,
        valid_from=date(2007, 1, 3),
    )


@pytest.mark.unit
def test_listing_id_includes_exchange_when_present() -> None:
    nyse = Listing(ticker="SE", exchange="nyse", valid_from=date(2017, 10, 20))
    nasdaq = Listing(ticker="SE", exchange="NASDAQ", valid_from=date(2017, 10, 20))
    assert nyse.listing_id != nasdaq.listing_id
    assert nyse.exchange == "NYSE"


@pytest.mark.unit
def test_unknown_occupancy_is_not_recycle_safe() -> None:
    listing = Listing.unknown_occupancy("msft", date(2020, 1, 2))
    assert listing.security_id is None
    assert listing.occupancy_known is False
    assert listing.listing_id == unknown_occupancy_listing_id(ticker="MSFT", exchange=None)
    assert listing.listing_id != occupancy_listing_id(
        ticker="MSFT",
        exchange=None,
        valid_from=date(2020, 1, 2),
    )


@pytest.mark.unit
def test_invalid_listing_interval_raises() -> None:
    with pytest.raises(DomainValidationError, match="valid_from must be earlier than valid_to"):
        Listing(ticker="X", valid_from=date(2020, 1, 1), valid_to=date(2020, 1, 1))
