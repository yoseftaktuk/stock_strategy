from datetime import datetime
from decimal import Decimal

from app.database.models import PortfolioSnapshotModel
from app.domain.models.portfolio import Portfolio


def to_domain(model: PortfolioSnapshotModel) -> Portfolio:
    return Portfolio(
        cash=model.cash,
        positions=(),
    )


def from_domain(portfolio: Portfolio, *, timestamp: datetime) -> PortfolioSnapshotModel:
    return PortfolioSnapshotModel(
        timestamp=timestamp,
        cash=portfolio.cash,
        equity=portfolio.equity,
        exposure=Decimal("0"),
        drawdown=Decimal("0"),
    )
