from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import PortfolioSnapshotModel
from app.database.repositories.portfolio import PostgresPortfolioRepository
from tests.fixtures.portfolios import SAMPLE_PORTFOLIO


@pytest.mark.integration
def test_portfolio_repository_save_and_get_latest(db_session: Session) -> None:
    repository = PostgresPortfolioRepository(db_session)
    timestamp = datetime(2024, 1, 2, 16, 0, tzinfo=timezone.utc)

    saved = repository.save_snapshot(SAMPLE_PORTFOLIO, timestamp=timestamp)
    db_session.commit()

    latest = repository.get_latest_snapshot()
    assert latest is not None
    assert latest.cash == SAMPLE_PORTFOLIO.cash
    assert saved.cash == SAMPLE_PORTFOLIO.cash

    model = db_session.scalar(
        select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.timestamp.desc()).limit(1)
    )
    assert model is not None
    assert model.equity == SAMPLE_PORTFOLIO.equity
