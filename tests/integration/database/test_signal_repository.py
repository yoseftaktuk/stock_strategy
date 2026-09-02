from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database.repositories.signals import PostgresSignalRepository
from app.domain.models.signal import MomentumSignal


@pytest.mark.integration
def test_signal_repository_save_and_get_signals(db_session: Session) -> None:
    repository = PostgresSignalRepository(db_session)
    signals = [
        MomentumSignal(
            symbol="AAPL",
            date=date(2024, 1, 2),
            momentum=Decimal("0.20"),
            rank=1,
            eligible=True,
        ),
        MomentumSignal(
            symbol="MSFT",
            date=date(2024, 1, 2),
            momentum=Decimal("0.10"),
            rank=2,
            eligible=True,
        ),
    ]
    repository.save_signals(signals)
    db_session.commit()

    loaded = repository.get_signals(date(2024, 1, 2))
    assert len(loaded) == 2
    assert loaded[0].rank == 1


@pytest.mark.integration
def test_signal_repository_get_latest_signals(db_session: Session) -> None:
    repository = PostgresSignalRepository(db_session)
    repository.save_signals(
        [
            MomentumSignal(
                symbol="AAPL",
                date=date(2024, 1, 3),
                momentum=Decimal("0.20"),
                rank=1,
                eligible=True,
            )
        ]
    )
    db_session.commit()

    latest = repository.get_latest_signals()
    assert len(latest) == 1
    assert latest[0].date == date(2024, 1, 3)
