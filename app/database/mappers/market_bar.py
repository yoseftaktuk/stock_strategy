from app.database.mappers import stock as stock_mapper
from app.database.models import MarketBarModel, StockModel
from app.domain.models.market_bar import MarketBar


def to_domain(model: MarketBarModel, *, symbol: str) -> MarketBar:
    return MarketBar(
        symbol=symbol,
        timestamp=model.timestamp,
        open=model.open,
        high=model.high,
        low=model.low,
        close=model.close,
        adjusted_close=model.adjusted_close,
        volume=model.volume,
    )


def from_domain(bar: MarketBar, *, stock_id: int) -> MarketBarModel:
    return MarketBarModel(
        stock_id=stock_id,
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        adjusted_close=bar.adjusted_close,
        volume=bar.volume,
    )


def resolve_stock_for_bar(session, bar: MarketBar) -> StockModel:
    return stock_mapper.resolve_stock_by_symbol(session, bar.symbol)
