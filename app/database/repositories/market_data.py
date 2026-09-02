from collections.abc import Sequence
from datetime import date, datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.mappers import market_bar as market_bar_mapper
from app.database.mappers import stock as stock_mapper
from app.database.models import MarketBarModel, StockModel
from app.domain.models.market_bar import MarketBar

DEFAULT_INSERT_BATCH_SIZE = 2000


class PostgresMarketDataRepository:
    def __init__(self, session: Session, *, batch_size: int = DEFAULT_INSERT_BATCH_SIZE) -> None:
        self._session = session
        self._batch_size = batch_size

    def save_bars(self, bars: Sequence[MarketBar]) -> int:
        if not bars:
            return 0

        stock_ids = self._resolve_stock_ids(bars)
        rows = [
            {
                "stock_id": stock_ids[bar.symbol.upper()],
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "adjusted_close": bar.adjusted_close,
                "volume": bar.volume,
            }
            for bar in bars
        ]

        inserted = 0
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            stmt = (
                insert(MarketBarModel)
                .values(batch)
                .on_conflict_do_nothing(constraint="uq_market_bars_stock_timestamp")
                .returning(MarketBarModel.id)
            )
            result = self._session.execute(stmt)
            inserted += len(result.all())

        self._session.flush()
        return inserted

    def get_bars(self, symbol: str, start: date, end: date) -> Sequence[MarketBar]:
        start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

        stmt = (
            select(MarketBarModel, StockModel.symbol)
            .join(StockModel, MarketBarModel.stock_id == StockModel.id)
            .where(
                StockModel.symbol == symbol.upper(),
                MarketBarModel.timestamp >= start_dt,
                MarketBarModel.timestamp <= end_dt,
            )
            .order_by(MarketBarModel.timestamp)
        )
        rows = self._session.execute(stmt).all()
        return [market_bar_mapper.to_domain(model, symbol=symbol_value) for model, symbol_value in rows]

    def get_latest_bar(self, symbol: str) -> MarketBar | None:
        stmt = (
            select(MarketBarModel, StockModel.symbol)
            .join(StockModel, MarketBarModel.stock_id == StockModel.id)
            .where(StockModel.symbol == symbol.upper())
            .order_by(desc(MarketBarModel.timestamp))
            .limit(1)
        )
        row = self._session.execute(stmt).first()
        if row is None:
            return None
        model, symbol_value = row
        return market_bar_mapper.to_domain(model, symbol=symbol_value)

    def _resolve_stock_ids(self, bars: Sequence[MarketBar]) -> dict[str, int]:
        stock_ids: dict[str, int] = {}
        for symbol in {bar.symbol.upper() for bar in bars}:
            stock = stock_mapper.resolve_stock_by_symbol(self._session, symbol)
            stock_ids[symbol] = stock.id
        return stock_ids
