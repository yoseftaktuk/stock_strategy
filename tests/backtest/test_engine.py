from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine, _monthly_rebalance_dates
from app.broker.simulated import SimulatedBroker
from app.domain.enums import OrderSide, RebalanceFrequency
from app.domain.execution import apply_slippage
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
