from decimal import Decimal

from app.domain.models.portfolio import Portfolio
from app.domain.models.position import Position

SAMPLE_POSITION = Position(
    symbol="AAPL",
    quantity=Decimal("10"),
    average_price=Decimal("150.00"),
    market_price=Decimal("154.00"),
)

SAMPLE_PORTFOLIO = Portfolio(
    cash=Decimal("50000.00"),
    positions=(SAMPLE_POSITION,),
)

SAMPLE_EMPTY_PORTFOLIO = Portfolio(cash=Decimal("100000.00"))
