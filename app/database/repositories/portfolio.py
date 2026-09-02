from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.mappers import portfolio as portfolio_mapper
from app.database.models import PortfolioSnapshotModel
from app.domain.models.portfolio import Portfolio


class PostgresPortfolioRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_snapshot(self, portfolio: Portfolio, timestamp: datetime) -> Portfolio:
        model = portfolio_mapper.from_domain(portfolio, timestamp=timestamp)
        self._session.add(model)
        self._session.flush()
        return portfolio_mapper.to_domain(model)

    def get_latest_snapshot(self) -> Portfolio | None:
        model = self._session.scalar(
            select(PortfolioSnapshotModel).order_by(desc(PortfolioSnapshotModel.timestamp)).limit(1)
        )
        if model is None:
            return None
        return portfolio_mapper.to_domain(model)
