from datetime import date
from decimal import Decimal

import pytest

from app.domain.exceptions import DomainValidationError
from app.domain.models.signal import MomentumSignal


@pytest.mark.unit
def test_signal_valid_construction() -> None:
    signal = MomentumSignal(
        symbol="AAPL",
        date=date(2024, 1, 2),
        momentum=Decimal("0.15"),
        rank=1,
        eligible=True,
    )
    assert signal.rank == 1
    assert signal.eligible is True


@pytest.mark.unit
def test_signal_rejects_negative_rank() -> None:
    with pytest.raises(DomainValidationError, match="rank must be non-negative"):
        MomentumSignal(
            symbol="AAPL",
            date=date(2024, 1, 2),
            momentum=Decimal("0.15"),
            rank=-1,
            eligible=True,
        )
