from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import StockModel
from app.domain.models.stock import Stock


def to_domain(model: StockModel) -> Stock:
    return Stock(
        symbol=model.symbol,
        exchange=model.exchange,
        currency=model.currency,
    )


def from_domain(stock: Stock) -> StockModel:
    return StockModel(
        symbol=stock.symbol,
        exchange=stock.exchange,
        currency=stock.currency,
        active=True,
    )


def resolve_stock(session: Session, stock: Stock) -> StockModel:
    existing = session.scalar(
        select(StockModel).where(
            StockModel.symbol == stock.symbol,
            StockModel.exchange == stock.exchange,
        )
    )
    if existing is not None:
        return existing

    model = from_domain(stock)
    session.add(model)
    session.flush()
    return model


def resolve_stock_by_symbol(session: Session, symbol: str, exchange: str = "NASDAQ") -> StockModel:
    return resolve_stock(session, Stock(symbol=symbol, exchange=exchange, currency="USD"))
