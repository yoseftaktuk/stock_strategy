from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine, _monthly_rebalance_dates
from app.broker.simulated import SimulatedBroker
from app.domain.enums import OrderSide, OrderStatus, OrderType, RebalanceFrequency
from app.domain.execution import apply_slippage
from app.domain.models.order import Order
from app.risk.risk_manager import RiskManager
from app.strategy.momentum import MomentumStrategy
from tests.fixtures.momentum import TEST_CONFIG, make_bar, make_series

START = date(2024, 1, 2)
END = date(2024, 3, 21)


def _market_data(count: int = 80) -> dict[str, list]:
    slopes = {
        "NVDA": Decimal("2"),
        "MSFT": Decimal("1.5"),
        "AAPL": Decimal("1"),
        "AMD": Decimal("0.5"),
    }
    data: dict[str, list] = {}
    for symbol, slope in slopes.items():
        adjusted = [Decimal("100") + slope * Decimal(index) for index in range(count)]
        data[symbol] = make_series(
            symbol,
            count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=adjusted,
            volume=2_000_000,
        )
    return data


def _config(**kwargs: object) -> BacktestConfig:
    values: dict[str, object] = {
        "start_date": START,
        "end_date": END,
        "initial_capital": Decimal("100000"),
        "commission_rate": Decimal("0"),
        "slippage_bps": Decimal("0"),
        "min_trade_value": Decimal("1"),
        "warmup_sessions": TEST_CONFIG.lookback_days + 1,
    }
    values.update(kwargs)
    return BacktestConfig(**values)  # type: ignore[arg-type]


def _engine(config: BacktestConfig, strategy: MomentumStrategy | None = None) -> tuple[BacktestEngine, SimulatedBroker]:
    broker = SimulatedBroker(
        initial_capital=config.initial_capital,
        commission_rate=config.commission_rate,
        slippage_bps=config.slippage_bps,
    )
    engine = BacktestEngine(
        strategy=strategy or MomentumStrategy(TEST_CONFIG),
        broker=broker,
        portfolio_service=PortfolioService(),
        order_service=OrderService(
            commission_rate=config.commission_rate,
            slippage_bps=config.slippage_bps,
        ),
        risk_manager=RiskManager(),
        config=config,
    )
    return engine, broker


@pytest.mark.backtest
def test_engine_end_to_end_is_deterministic() -> None:
    market_data = _market_data()
    config = _config()
    first, _ = _engine(config)
    second, _ = _engine(config)
    result_a = first.run(START, END, market_data=market_data)
    result_b = second.run(START, END, market_data=market_data)
    assert result_a.equity_curve == result_b.equity_curve
    assert result_a.fills == result_b.fills
    assert result_a.orders == result_b.orders
    assert result_a.total_commission == result_b.total_commission
    assert result_a.total_slippage == result_b.total_slippage
    assert result_a.final_equity == result_b.final_equity
    assert result_a.total_return == result_b.total_return
    assert result_a.number_of_trades == result_b.number_of_trades
    assert result_a.final_equity > 0
    assert result_a.orders
    assert result_a.equity_curve[0].date == START
    sell_indices = [index for index, order in enumerate(result_a.orders) if order.side == OrderSide.SELL]
    buy_indices = [index for index, order in enumerate(result_a.orders) if order.side == OrderSide.BUY]
    if sell_indices and buy_indices:
        assert min(sell_indices) < min(buy_indices)


@pytest.mark.backtest
def test_signal_at_t_executes_at_next_open() -> None:
    market_data = _market_data()
    execution_date = date(2024, 2, 2)
    signal_date = date(2024, 2, 1)
    for symbol, bars in market_data.items():
        for index, bar in enumerate(bars):
            if bar.timestamp.date() == execution_date:
                bars[index] = make_bar(
                    symbol,
                    execution_date,
                    close=bar.close,
                    open=Decimal("40"),
                    adjusted_close=bar.adjusted_close,
                    volume=bar.volume,
                )
            if bar.timestamp.date() == signal_date:
                bars[index] = make_bar(
                    symbol,
                    signal_date,
                    close=Decimal("80"),
                    open=bar.open,
                    adjusted_close=bar.adjusted_close,
                    volume=bar.volume,
                )
    config = _config(slippage_bps=Decimal("10"), commission_rate=Decimal("0"))
    engine, _ = _engine(config)
    result = engine.run(START, END, market_data=market_data)
    execution_fills = [fill for fill in result.fills if fill.timestamp.date() == execution_date]
    assert execution_fills
    expected = apply_slippage(OrderSide.BUY, Decimal("40"), Decimal("10"))
    for fill in execution_fills:
        if fill.price < Decimal("50"):
            assert fill.price == expected
            assert fill.price != Decimal("80")


@pytest.mark.backtest
def test_look_ahead_future_bars_do_not_change_t_decision() -> None:
    market_data = _market_data()
    config = _config()
    engine_a, _ = _engine(config)
    result_a = engine_a.run(START, END, market_data=market_data)

    mutated = deepcopy(market_data)
    cutoff = date(2024, 2, 3)
    for symbol, bars in mutated.items():
        updated = []
        for bar in bars:
            if bar.timestamp.date() >= cutoff:
                updated.append(
                    make_bar(
                        symbol,
                        bar.timestamp.date(),
                        close=Decimal("9"),
                        open=Decimal("9"),
                        adjusted_close=Decimal("9"),
                        volume=1,
                    )
                )
            else:
                updated.append(bar)
        mutated[symbol] = updated

    engine_b, _ = _engine(config)
    result_b = engine_b.run(START, END, market_data=mutated)
    first_execution = date(2024, 2, 2)
    fills_a = [fill for fill in result_a.fills if fill.timestamp.date() == first_execution]
    fills_b = [fill for fill in result_b.fills if fill.timestamp.date() == first_execution]
    assert fills_a == fills_b
    assert fills_a


@pytest.mark.backtest
def test_monthly_rebalance_is_first_trading_day_of_month() -> None:
    trading_dates = [START + timedelta(days=offset) for offset in range(80)]
    rebalance_dates = _monthly_rebalance_dates(trading_dates, TEST_CONFIG.lookback_days + 1)
    assert date(2024, 1, 2) not in rebalance_dates
    assert date(2024, 2, 1) in rebalance_dates
    assert date(2024, 3, 1) in rebalance_dates

    market_data = _market_data()
    engine, _ = _engine(_config())
    result = engine.run(START, END, market_data=market_data)
    fill_dates = sorted({fill.timestamp.date() for fill in result.fills})
    assert date(2024, 2, 2) in fill_dates
    assert date(2024, 1, 3) not in fill_dates
    assert result.equity_curve[-1].date >= date(2024, 3, 1)


@pytest.mark.backtest
def test_weekly_frequency_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        BacktestConfig(
            start_date=START,
            end_date=END,
            rebalance_frequency=RebalanceFrequency.WEEKLY,
        )


@pytest.mark.backtest
def test_no_negative_cash_or_short_positions() -> None:
    engine, broker = _engine(_config())
    result = engine.run(START, END, market_data=_market_data())
    assert all(point.cash >= 0 for point in result.equity_curve)
    assert all(position.quantity >= 0 for position in broker.get_positions())


@pytest.mark.backtest
def test_result_report_contains_headings() -> None:
    engine, _ = _engine(_config())
    report = engine.run(START, END, market_data=_market_data()).format_report()
    assert "BACKTEST RESULT" in report
    assert "Sharpe:" in report
    assert "Max Drawdown:" in report
    assert "Fills:" in report
    assert "Universe:" in report
    assert "explicit" in report


@pytest.mark.backtest
def test_short_calendar_records_no_rebalance_warning() -> None:
    market_data = {"AAPL": make_series("AAPL", 3, start=START, close=Decimal("50"), volume=2_000_000)}
    engine, _ = _engine(_config())
    result = engine.run(START, END, market_data=market_data)
    assert result.number_of_trades == 0
    assert result.warnings
    assert "warmup sessions" in result.warnings[0]
    assert "Warnings:" in result.format_report()


@pytest.mark.backtest
def test_fills_never_occur_on_signal_dates() -> None:
    market_data = _market_data()
    trading_dates = sorted(
        {bar.timestamp.date() for bars in market_data.values() for bar in bars if START <= bar.timestamp.date() <= END}
    )
    rebalance_dates = _monthly_rebalance_dates(trading_dates, TEST_CONFIG.lookback_days + 1)
    engine, _ = _engine(_config())
    result = engine.run(START, END, market_data=market_data)
    fill_dates = {fill.timestamp.date() for fill in result.fills}
    assert fill_dates
    assert fill_dates.isdisjoint(rebalance_dates)
    for fill in result.fills:
        assert fill.timestamp.date() != START or START not in rebalance_dates


@pytest.mark.backtest
def test_every_fill_uses_next_open_with_slippage() -> None:
    market_data = _market_data()
    slippage_bps = Decimal("10")
    engine, _ = _engine(_config(slippage_bps=slippage_bps, commission_rate=Decimal("0")))
    result = engine.run(START, END, market_data=market_data)
    assert result.fills
    orders_by_id = {order.client_order_id: order for order in result.orders}
    opens_by_date: dict[date, dict[str, Decimal]] = {}
    for symbol, bars in market_data.items():
        for bar in bars:
            session = bar.timestamp.date()
            if START <= session <= END:
                opens_by_date.setdefault(session, {})[symbol] = bar.open
    for fill in result.fills:
        order = orders_by_id[fill.order_id]
        market = opens_by_date[fill.timestamp.date()][fill.symbol]
        expected = apply_slippage(order.side, market, slippage_bps)
        assert fill.price == expected
        assert fill.market_price == market


@pytest.mark.backtest
def test_last_session_rebalance_warns_and_does_not_fill_after_end() -> None:
    end = date(2024, 2, 1)
    market_data = _market_data(count=31)
    engine, _ = _engine(_config(end_date=end))
    result = engine.run(START, end, market_data=market_data)
    assert any("Final rebalance was not executed" in warning for warning in result.warnings)
    assert all(fill.timestamp.date() <= end for fill in result.fills)
    assert all(fill.timestamp.date() != end for fill in result.fills)


@pytest.mark.backtest
def test_extreme_first_close_marks_series_unusable_without_dropping_membership() -> None:
    market_data = _market_data()
    market_data["RICH"] = make_series(
        "RICH",
        80,
        start=START,
        close=Decimal("5000"),
        volume=2_000_000,
    )
    engine, _ = _engine(_config())
    result = engine.run(START, END, market_data=market_data)
    extreme = [warning for warning in result.warnings if "Unusable price series" in warning]
    assert extreme
    assert "RICH" in extreme[0]
    assert "PIT membership was not dropped" in extreme[0]
    assert all(fill.symbol != "RICH" for fill in result.fills)
    assert "RICH" in result.unusable_symbols
    assert "RICH" in result.priced_symbols


@pytest.mark.backtest
def test_risk_rejected_orders_are_rejected_and_produce_no_fill() -> None:
    class ForcedShortOrderService:
        def create_orders_from_targets(self, *args: object, **kwargs: object) -> list[Order]:
            return [
                Order(
                    symbol="NVDA",
                    side=OrderSide.SELL,
                    quantity=Decimal("1"),
                    order_type=OrderType.MARKET,
                    limit_price=None,
                    client_order_id="risk-reject-0001",
                )
            ]

    config = _config()
    broker = SimulatedBroker(
        initial_capital=config.initial_capital,
        commission_rate=config.commission_rate,
        slippage_bps=config.slippage_bps,
    )
    engine = BacktestEngine(
        strategy=MomentumStrategy(TEST_CONFIG),
        broker=broker,
        portfolio_service=PortfolioService(),
        order_service=ForcedShortOrderService(),  # type: ignore[arg-type]
        risk_manager=RiskManager(),
        config=config,
    )
    result = engine.run(START, END, market_data=_market_data())
    assert result.orders
    assert all(order.status == OrderStatus.REJECTED for order in result.orders)
    assert result.fills == ()
    assert result.total_commission == Decimal("0")
    assert result.total_slippage == Decimal("0")
    assert broker.get_account().cash == config.initial_capital


@pytest.mark.backtest
def test_result_accounting_invariants() -> None:
    config = _config(slippage_bps=Decimal("10"), commission_rate=Decimal("0.0005"))
    engine, broker = _engine(config)
    result = engine.run(START, END, market_data=_market_data())
    assert result.number_of_trades == len(result.fills)
    assert result.total_commission == sum((fill.commission for fill in result.fills), start=Decimal("0"))
    assert result.total_slippage == sum((fill.slippage for fill in result.fills), start=Decimal("0"))
    assert result.total_return == pytest.approx(float(result.final_equity / result.initial_capital - 1))
    orders_by_id = {order.client_order_id: order for order in result.orders}
    for fill in result.fills:
        assert fill.order_id in orders_by_id
        assert sum(1 for order in result.orders if order.client_order_id == fill.order_id) == 1
        assert orders_by_id[fill.order_id].status == OrderStatus.FILLED
    rejected = [order for order in result.orders if order.status == OrderStatus.REJECTED]
    rejected_ids = {order.client_order_id for order in rejected}
    assert all(fill.order_id not in rejected_ids for fill in result.fills)
    cash = result.initial_capital
    for fill in result.fills:
        order = orders_by_id[fill.order_id]
        gross = fill.quantity * fill.price
        if order.side == OrderSide.BUY:
            cash -= gross + fill.commission
        else:
            cash += gross - fill.commission
    assert cash == result.equity_curve[-1].cash
    account = broker.get_account()
    assert account.equity == result.final_equity
    marked = account.cash + sum((position.market_value for position in account.positions), start=Decimal("0"))
    assert marked == result.final_equity
    filled = [order for order in result.orders if order.status == OrderStatus.FILLED]
    assert len(result.fills) == len(filled)
