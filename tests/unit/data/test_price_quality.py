from datetime import date
from decimal import Decimal

import pytest

from app.data.price_quality import assess_price_series, unusable_symbols
from tests.fixtures.momentum import make_series


@pytest.mark.unit
def test_normal_series_is_usable() -> None:
    bars = make_series("AAA", 10, start=date(2024, 1, 2), close=Decimal("50"))
    assessment = assess_price_series(bars)
    assert assessment.usable is True
    assert assessment.reason is None
    assert assessment.symbol == "AAA"


@pytest.mark.unit
def test_azo_class_high_first_close_is_usable() -> None:
    bars = make_series("AZO", 10, start=date(2024, 1, 2), close=Decimal("3200"))
    assessment = assess_price_series(bars)
    assert assessment.usable is True
    assert assessment.reason is None
    assert unusable_symbols({"AZO": bars}) == {}


@pytest.mark.unit
def test_mtd_nvr_class_high_first_close_is_usable() -> None:
    mtd = make_series("MTD", 5, start=date(2024, 1, 2), close=Decimal("1400"))
    nvr = make_series("NVR", 5, start=date(2024, 1, 2), close=Decimal("7500"))
    assert assess_price_series(mtd).usable is True
    assert assess_price_series(nvr).usable is True
    assert unusable_symbols({"MTD": mtd, "NVR": nvr}) == {}


@pytest.mark.unit
def test_empty_series_is_not_classified_unusable() -> None:
    assert unusable_symbols({"MISS": []}) == {}
    assessment = assess_price_series([])
    assert assessment.usable is True
    assert assessment.reason is None
