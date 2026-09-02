from datetime import date
from decimal import Decimal

import pytest

from app.data.price_quality import (
    DEFAULT_EXTREME_FIRST_CLOSE,
    REASON_EXTREME_FIRST_CLOSE,
    assess_price_series,
    unusable_symbols,
)
from tests.fixtures.momentum import make_series


@pytest.mark.unit
def test_normal_series_is_usable() -> None:
    bars = make_series("AAA", 10, start=date(2024, 1, 2), close=Decimal("50"))
    assessment = assess_price_series(bars)
    assert assessment.usable is True
    assert assessment.reason is None
    assert assessment.symbol == "AAA"


@pytest.mark.unit
def test_extreme_first_close_is_unusable() -> None:
    bars = make_series("RICH", 10, start=date(2024, 1, 2), close=Decimal("5000"))
    assessment = assess_price_series(bars)
    assert assessment.usable is False
    assert assessment.reason == REASON_EXTREME_FIRST_CLOSE
    assert "RICH" in unusable_symbols({"RICH": bars})


@pytest.mark.unit
def test_threshold_boundary_is_unusable() -> None:
    bars = make_series(
        "EDGE",
        5,
        start=date(2024, 1, 2),
        close=DEFAULT_EXTREME_FIRST_CLOSE,
    )
    assert assess_price_series(bars).usable is False


@pytest.mark.unit
def test_high_but_valid_first_close_is_usable() -> None:
    bars = make_series("NVRX", 5, start=date(2024, 1, 2), close=Decimal("917"))
    assert assess_price_series(bars).usable is True
    assert unusable_symbols({"NVRX": bars}) == {}


@pytest.mark.unit
def test_empty_series_is_not_classified_unusable() -> None:
    assert unusable_symbols({"MISS": []}) == {}
    assessment = assess_price_series([])
    assert assessment.usable is True
    assert assessment.reason is None
