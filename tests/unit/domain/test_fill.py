from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.fill import Fill


@pytest.mark.unit
def test_fill_valid_construction() -> None:
    fill = Fill(
        order_id="order-001",
        symbol="AAPL",
        quantity=Decimal("10"),
        price=Decimal("154.00"),
        commission=Decimal("1.00"),
        timestamp=datetime(2024, 1, 2, 16, 5, tzinfo=timezone.utc),
    )
    assert fill.price == Decimal("154.00")


@pytest.mark.unit
def test_fill_rejects_non_positive_quantity() -> None:
    with pytest.raises(DomainValidationError, match="quantity must be greater than zero"):
        Fill(
            order_id="order-001",
            symbol="AAPL",
            quantity=Decimal("0"),
            price=Decimal("154.00"),
            commission=Decimal("1.00"),
            timestamp=datetime(2024, 1, 2, 16, 5, tzinfo=timezone.utc),
        )


@pytest.mark.unit
def test_fill_rejects_negative_commission() -> None:
    with pytest.raises(DomainValidationError, match="commission must be non-negative"):
        Fill(
            order_id="order-001",
            symbol="AAPL",
            quantity=Decimal("10"),
            price=Decimal("154.00"),
            commission=Decimal("-1.00"),
            timestamp=datetime(2024, 1, 2, 16, 5, tzinfo=timezone.utc),
        )
