from collections.abc import Sequence
from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.mappers import signal as signal_mapper
from app.database.models import SignalModel, StockModel
from app.domain.models.signal import MomentumSignal


class PostgresSignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_signals(self, signals: Sequence[MomentumSignal]) -> None:
        for signal in signals:
            stock = signal_mapper.resolve_stock_for_signal(self._session, signal)
            model = signal_mapper.from_domain(signal, stock_id=stock.id)
            self._session.add(model)
        self._session.flush()

    def get_signals(self, signal_date: date) -> Sequence[MomentumSignal]:
        stmt = (
            select(SignalModel, StockModel.symbol)
            .join(StockModel, SignalModel.stock_id == StockModel.id)
            .where(SignalModel.signal_date == signal_date)
            .order_by(SignalModel.rank)
        )
        rows = self._session.execute(stmt).all()
        return [signal_mapper.to_domain(model, symbol=symbol_value) for model, symbol_value in rows]

    def get_latest_signals(self) -> Sequence[MomentumSignal]:
        latest_date = self._session.scalar(select(SignalModel.signal_date).order_by(desc(SignalModel.signal_date)).limit(1))
        if latest_date is None:
            return []
        return self.get_signals(latest_date)
