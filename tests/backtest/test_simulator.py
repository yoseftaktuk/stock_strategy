from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.enums import OrderSide, OrderStatus, OrderType
from app.domain.execution import apply_slippage, commission_on
from app.domain.models.order import Order
from app.broker.simulated import SimulatedBroker

UTC = timezone.utc
SESSION = datetime(2024, 2, 1, 9, 30, tzinfo=UTC)


def _broker(
    *,
    capital: Decimal = Decimal("100000"),
    commission_rate: Decimal = Decimal("0.0005"),
    slippage_bps: Decimal = Decimal("10"),
) -> SimulatedBroker:
    broker = SimulatedBroker(
        initial_capital=capital,
        commission_rate=commission_rate,
        slippage_bps=slippage_bps,
    )
    broker.connect()
    broker.set_market_prices({"AAPL": Decimal("100")}, SESSION)
    return broker


def _order(side: OrderSide, quantity: Decimal, symbol: str = "AAPL") -> Order:
    return Order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id=f"{side.value}-{quantity}",
    )


@pytest.mark.backtest
def test_buy_decreases_cash_and_adds_position() -> None:
    broker = _broker()
    filled = broker.submit_order(_order(OrderSide.BUY, Decimal("10")))
    assert filled.status == OrderStatus.FILLED
    fill_price = apply_slippage(OrderSide.BUY, Decimal("100"), Decimal("10"))
    trade_value = Decimal("10") * fill_price
    commission = commission_on(trade_value, Decimal("0.0005"))
    assert broker.get_account().cash == Decimal("100000") - trade_value - commission
    position = broker.get_positions()[0]
    assert position.symbol == "AAPL"
    assert position.quantity == Decimal("10")
    assert position.average_price == fill_price
    assert broker.total_commission == commission
    assert broker.total_slippage == (fill_price - Decimal("100")) * Decimal("10")


@pytest.mark.backtest
def test_sell_increases_cash_and_reduces_position() -> None:
    broker = _broker()
    broker.submit_order(_order(OrderSide.BUY, Decimal("10")))
    cash_after_buy = broker.get_account().cash
    filled = broker.submit_order(_order(OrderSide.SELL, Decimal("4")))
    assert filled.status == OrderStatus.FILLED
    fill_price = apply_slippage(OrderSide.SELL, Decimal("100"), Decimal("10"))
    trade_value = Decimal("4") * fill_price
    commission = commission_on(trade_value, Decimal("0.0005"))
    assert broker.get_account().cash == cash_after_buy + trade_value - commission
    assert broker.get_positions()[0].quantity == Decimal("6")


@pytest.mark.backtest
def test_insufficient_cash_rejects_buy() -> None:
    broker = _broker(capital=Decimal("1000"))
    filled = broker.submit_order(_order(OrderSide.BUY, Decimal("100")))
    assert filled.status == OrderStatus.REJECTED
    assert broker.get_account().cash == Decimal("1000")
    assert broker.get_positions() == []


@pytest.mark.backtest
def test_short_selling_is_rejected() -> None:
    broker = _broker()
    filled = broker.submit_order(_order(OrderSide.SELL, Decimal("1")))
    assert filled.status == OrderStatus.REJECTED
    assert broker.get_positions() == []
    assert broker.get_account().cash == Decimal("100000")


@pytest.mark.backtest
def test_full_close_removes_position() -> None:
    broker = _broker()
    broker.submit_order(_order(OrderSide.BUY, Decimal("10")))
    filled = broker.submit_order(_order(OrderSide.SELL, Decimal("10")))
    assert filled.status == OrderStatus.FILLED
    assert broker.get_positions() == []


@pytest.mark.backtest
def test_rejected_orders_do_not_create_fills_or_costs() -> None:
    broker = _broker(capital=Decimal("1000"))
    filled = broker.submit_order(_order(OrderSide.BUY, Decimal("100")))
    assert filled.status == OrderStatus.REJECTED
    assert broker.get_fills() == []
    assert broker.total_commission == Decimal("0")
    assert broker.total_slippage == Decimal("0")
    assert broker.get_account().cash == Decimal("1000")


@pytest.mark.backtest
def test_successful_order_records_one_fill_with_market_price() -> None:
    broker = _broker()
    filled = broker.submit_order(_order(OrderSide.BUY, Decimal("10")))
    assert filled.status == OrderStatus.FILLED
    fills = broker.get_fills()
    assert len(fills) == 1
    fill = fills[0]
    assert fill.market_price == Decimal("100")
    assert fill.price == apply_slippage(OrderSide.BUY, Decimal("100"), Decimal("10"))
    assert fill.portfolio_value == broker.get_account().equity
    assert fill.cash == broker.get_account().cash
    assert fill.position_quantity == Decimal("10")
    assert fill.slippage == abs(fill.price - fill.market_price) * fill.quantity


@pytest.mark.backtest
def test_mark_to_market_unvalued_excludes_position_from_equity() -> None:
    broker = _broker()
    broker.submit_order(_order(OrderSide.BUY, Decimal("10")))
    broker.mark_to_market({"AAPL": Decimal("110")})
    valued_equity = broker.get_account().equity
    broker.mark_to_market({}, unvalued={"AAPL"})
    account = broker.get_account()
    position = account.positions[0]
    assert position.valued is False
    assert position.market_value == Decimal("0")
    assert account.equity == account.cash
    assert account.equity != valued_equity
    broker.mark_to_market({"AAPL": Decimal("110")})
    assert broker.get_positions()[0].valued is True
    assert broker.get_account().equity == valued_equity


@pytest.mark.backtest
def test_apply_slippage_helpers() -> None:
    assert apply_slippage(OrderSide.BUY, Decimal("100"), Decimal("10")) == Decimal("100.10")
    assert apply_slippage(OrderSide.SELL, Decimal("100"), Decimal("10")) == Decimal("99.90")
    assert commission_on(Decimal("10000"), Decimal("0.0005")) == Decimal("5")
