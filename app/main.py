import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.application.rebalance_service import RebalanceService
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.metrics import MetricsCalculator
from app.broker.ibkr.broker import IBKRBroker
from app.broker.ibkr.client import IBKRClient
from app.broker.simulated import SimulatedBroker
from app.config.settings import Settings
from app.data.factory import create_market_data_provider
from app.data.market_data import MarketDataService
from app.database.repositories.market_data import PostgresMarketDataRepository
from app.database.session import create_session
from app.domain.enums import TradingMode
from app.risk.kill_switch import KillSwitch
from app.risk.risk_manager import RiskManager
from app.strategy.config import MomentumConfig
from app.strategy.momentum import MomentumStrategy

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    settings: Settings
    session: Session
    broker: SimulatedBroker | IBKRBroker
    market_data_service: MarketDataService
    strategy: MomentumStrategy
    rebalance_service: RebalanceService
    backtest_engine: BacktestEngine


def build_container(settings: Settings | None = None) -> AppContainer:
    """Composition root: wire all dependencies based on settings."""
    if settings is None:
        settings = Settings()

    slippage_bps = settings.slippage * Decimal("10000")
    simulated_broker = SimulatedBroker(
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0.0005"),
        slippage_bps=slippage_bps,
    )
    if settings.trading_mode == TradingMode.BACKTEST:
        broker: SimulatedBroker | IBKRBroker = simulated_broker
    else:
        broker = IBKRBroker(IBKRClient(settings))

    session = create_session(settings)
    provider = create_market_data_provider(settings)
    repository = PostgresMarketDataRepository(
        session,
        batch_size=settings.market_data_insert_batch_size,
    )
    market_data_service = MarketDataService(provider=provider, repository=repository)

    momentum_config = MomentumConfig(
        lookback_days=settings.momentum_lookback,
        skip_days=settings.momentum_skip,
        top_n=settings.top_n,
        min_price=settings.min_price,
        liquidity_window_days=settings.liquidity_window_days,
        min_dollar_volume=settings.min_dollar_volume,
    )
    strategy = MomentumStrategy(momentum_config)

    portfolio_service = PortfolioService()
    order_service = OrderService(commission_rate=Decimal("0.0005"), slippage_bps=slippage_bps)
    risk_manager = RiskManager()
    kill_switch = KillSwitch()

    rebalance_service = RebalanceService(
        market_data_service=market_data_service,
        strategy=strategy,
        portfolio_service=portfolio_service,
        order_service=order_service,
        risk_manager=risk_manager,
        broker=broker,
        kill_switch=kill_switch,
    )

    backtest_config = BacktestConfig(
        start_date=date(2015, 1, 1),
        end_date=date(2025, 12, 31),
        slippage_bps=slippage_bps,
        warmup_sessions=momentum_config.lookback_days + 1,
        symbols=tuple(settings.universe),
    )
    backtest_engine = BacktestEngine(
        strategy=strategy,
        broker=simulated_broker,
        portfolio_service=portfolio_service,
        order_service=order_service,
        risk_manager=risk_manager,
        config=backtest_config,
        metrics_calculator=MetricsCalculator(),
    )

    return AppContainer(
        settings=settings,
        session=session,
        broker=broker,
        market_data_service=market_data_service,
        strategy=strategy,
        rebalance_service=rebalance_service,
        backtest_engine=backtest_engine,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    container = build_container()
    logger.info("Momentum Trader started in %s mode", container.settings.trading_mode.value)
    logger.info("Broker: %s", type(container.broker).__name__)


if __name__ == "__main__":
    main()
