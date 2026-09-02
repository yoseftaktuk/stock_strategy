from datetime import date
from decimal import Decimal

import pytest

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.broker.simulated import SimulatedBroker
from app.data.identity_quality import REASON_IDENTITY_MISMATCH
from app.domain.enums import OrderSide
from app.risk.risk_manager import RiskManager
from app.security_master.seed import load_known_identities_catalog
from app.strategy.momentum import MomentumStrategy
from app.universe.factory import HISTORICAL_SP500
from app.universe.memory import InMemoryUniverseProvider
from tests.fixtures.momentum import TEST_CONFIG, make_series
from tests.fixtures.universe import membership

START = date(2024, 1, 2)
END = date(2024, 3, 21)


def _engine(*, universe=None, universe_kind: str | None = None, master=None) -> BacktestEngine:
    config = BacktestConfig(
        start_date=START,
        end_date=END,
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_trade_value=Decimal("1"),
        warmup_sessions=TEST_CONFIG.lookback_days + 1,
        universe_kind=universe_kind,
    )
    return BacktestEngine(
        strategy=MomentumStrategy(TEST_CONFIG),
        broker=SimulatedBroker(
            initial_capital=config.initial_capital,
            commission_rate=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
        portfolio_service=PortfolioService(),
        order_service=OrderService(commission_rate=Decimal("0"), slippage_bps=Decimal("0")),
        risk_manager=RiskManager(),
        config=config,
        universe_provider=universe,
        security_master=master,
    )


def _qty(result, symbol: str) -> Decimal:
    orders = {order.client_order_id: order for order in result.orders}
    quantity = Decimal("0")
    for fill in result.fills:
        if fill.symbol != symbol:
            continue
        if orders[fill.order_id].side == OrderSide.BUY:
            quantity += fill.quantity
        else:
            quantity -= fill.quantity
    return quantity


@pytest.mark.backtest
def test_identity_mismatch_cannot_fill_and_stays_in_pit() -> None:
    universe = InMemoryUniverseProvider(
        (
            membership("KEEP", date(2010, 1, 1)),
            membership("HAR", date(2006, 2, 1), date(2017, 3, 13)),
        )
    )
    keep_count = (END - START).days + 1
    keep_adj = [Decimal("100") + Decimal("1") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "KEEP": make_series(
            "KEEP",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=keep_adj,
            volume=2_000_000,
        ),
        "HAR": make_series(
            "HAR",
            keep_count,
            start=date(2015, 1, 2),
            close=Decimal("50"),
            volume=2_000_000,
        ),
    }
    engine = _engine(
        universe=universe,
        universe_kind=HISTORICAL_SP500,
        master=load_known_identities_catalog(),
    )
    result = engine.run(date(2015, 1, 2), date(2015, 3, 21), market_data=market_data)
    assert universe.get_symbols(date(2015, 2, 1)) == ["HAR", "KEEP"]
    assert "HAR" in result.unusable_symbols
    assert all(fill.symbol != "HAR" for fill in result.fills)
    assert "PIT membership was not dropped" in " ".join(result.warnings)


@pytest.mark.backtest
def test_identity_mismatch_reason_is_not_a_ticker_blacklist() -> None:
    universe = InMemoryUniverseProvider((membership("HAR", date(2006, 2, 1), date(2017, 3, 13)),))
    bars = make_series("HAR", 80, start=date(2015, 1, 2), close=Decimal("50"), volume=2_000_000)
    engine = _engine(
        universe=universe,
        universe_kind=HISTORICAL_SP500,
        master=load_known_identities_catalog(),
    )
    result = engine.run(date(2015, 1, 2), date(2015, 3, 21), market_data={"HAR": bars})
    assert result.unusable_symbols == ("HAR",)
    assert REASON_IDENTITY_MISMATCH in " ".join(result.warnings)
    assert universe.get_symbols(date(2015, 2, 1)) == ["HAR"]


@pytest.mark.backtest
def test_xyz_remapped_history_remains_usable() -> None:
    universe = InMemoryUniverseProvider((membership("XYZ", date(2024, 1, 1)),))
    keep_count = (END - START).days + 1
    adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(keep_count)]
    market_data = {
        "XYZ": make_series(
            "XYZ",
            keep_count,
            start=START,
            close=Decimal("50"),
            adjusted_closes=adj,
            volume=2_000_000,
        )
    }
    engine = _engine(
        universe=universe,
        universe_kind=HISTORICAL_SP500,
        master=load_known_identities_catalog(),
    )
    result = engine.run(START, END, market_data=market_data)
    assert "XYZ" not in result.unusable_symbols
    assert any(fill.symbol == "XYZ" for fill in result.fills)
    assert _qty(result, "XYZ") > 0


@pytest.mark.backtest
def test_tko_predecessor_bars_do_not_enter_lookback() -> None:
    universe = InMemoryUniverseProvider((membership("TKO", date(2023, 9, 12)),))
    early = make_series(
        "TKO",
        11,
        start=date(2023, 9, 1),
        close=Decimal("10.67"),
        volume=2_000_000,
    )
    later_count = 80
    adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(later_count)]
    later = make_series(
        "TKO",
        later_count,
        start=date(2023, 9, 12),
        close=Decimal("80"),
        adjusted_closes=adj,
        volume=2_000_000,
    )
    engine = _engine(
        universe=universe,
        universe_kind=HISTORICAL_SP500,
        master=load_known_identities_catalog(),
    )
    result = engine.run(date(2023, 9, 12), date(2023, 12, 1), market_data={"TKO": [*early, *later]})
    assert "TKO" not in result.unusable_symbols
    assert result.fills
    assert all(fill.symbol == "TKO" for fill in result.fills)
    assert all(fill.timestamp.date() >= date(2023, 9, 12) for fill in result.fills)


@pytest.mark.backtest
def test_pit_ticker_can_fill_from_vendor_symbol_bars() -> None:
    start = date(2020, 1, 2)
    end = date(2020, 3, 21)
    universe = InMemoryUniverseProvider((membership("ANTM", date(2002, 7, 25), date(2022, 6, 28)),))
    count = (end - start).days + 1
    adj = [Decimal("100") + Decimal("2") * Decimal(index) for index in range(count)]
    elv_bars = make_series(
        "ELV",
        count,
        start=start,
        close=Decimal("80"),
        adjusted_closes=adj,
        volume=2_000_000,
    )
    engine = _engine(
        universe=universe,
        universe_kind=HISTORICAL_SP500,
        master=load_known_identities_catalog(),
    )
    result = engine.run(start, end, market_data={"ANTM": elv_bars})
    assert universe.get_symbols(start) == ["ANTM"]
    assert "ANTM" not in result.unusable_symbols
    assert any(fill.symbol == "ANTM" for fill in result.fills)
