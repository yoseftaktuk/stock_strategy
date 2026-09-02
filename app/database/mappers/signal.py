from app.database.mappers import stock as stock_mapper
from app.database.models import SignalModel, StockModel
from app.domain.models.signal import MomentumSignal


def to_domain(model: SignalModel, *, symbol: str) -> MomentumSignal:
    return MomentumSignal(
        symbol=symbol,
        date=model.signal_date,
        momentum=model.momentum,
        rank=model.rank,
        eligible=model.eligible,
    )


def from_domain(signal: MomentumSignal, *, stock_id: int) -> SignalModel:
    return SignalModel(
        stock_id=stock_id,
        signal_date=signal.date,
        momentum=signal.momentum,
        rank=signal.rank,
        eligible=signal.eligible,
    )


def resolve_stock_for_signal(session, signal: MomentumSignal) -> StockModel:
    return stock_mapper.resolve_stock_by_symbol(session, signal.symbol)
