from app.database.models import FillModel
from app.domain.models.fill import Fill


def to_domain(model: FillModel, *, order_client_id: str) -> Fill:
    return Fill(
        order_id=order_client_id,
        symbol=model.symbol,
        quantity=model.quantity,
        price=model.price,
        commission=model.commission,
        timestamp=model.executed_at,
    )


def from_domain(fill: Fill, *, order_db_id: int) -> FillModel:
    return FillModel(
        order_id=order_db_id,
        broker_execution_id=None,
        symbol=fill.symbol,
        quantity=fill.quantity,
        price=fill.price,
        commission=fill.commission,
        executed_at=fill.timestamp,
    )
