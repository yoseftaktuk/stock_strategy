from datetime import date
from decimal import Decimal

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.broker.interface import Broker
from app.data.market_data import MarketDataService
from app.domain.models.market_bar import MarketBar
from app.risk.kill_switch import KillSwitch
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy


class RebalanceService:
    def __init__(
        self,
        market_data_service: MarketDataService,
        strategy: Strategy,
        portfolio_service: PortfolioService,
        order_service: OrderService,
        risk_manager: RiskManager,
        broker: Broker,
        kill_switch: KillSwitch,
    ) -> None:
        self._market_data_service = market_data_service
        self._strategy = strategy
        self._portfolio_service = portfolio_service
        self._order_service = order_service
        self._risk_manager = risk_manager
        self._broker = broker
        self._kill_switch = kill_switch

    def rebalance(self, as_of: date) -> None:
        """
        Orchestrate a portfolio rebalance.

        Future flow:
        1. Validate system
        2. Get account
        3. Get current positions
        4. Get market data
        5. Generate strategy signals
        6. Build target portfolio
        7. Generate orders
        8. Validate orders through RiskManager
        9. Submit orders
        10. Reconcile portfolio
        """
        if self._kill_switch.is_enabled():
            return

        if not self._broker.is_connected():
            self._broker.connect()

        account = self._broker.get_account()
        _ = self._broker.get_positions()

        market_data: dict[str, list[MarketBar]] = {}
        symbols: list[str] = []
        for symbol in symbols:
            market_data[symbol] = list(
                self._market_data_service.get_history(symbol, as_of, as_of)
            )

        signals = self._strategy.generate_signals(market_data, as_of)
        target = self._portfolio_service.build_target_portfolio(signals)
        orders = self._order_service.create_orders_from_targets(
            account,
            target,
            prices={},
            min_trade_value=Decimal("0"),
            as_of=as_of,
        )

        for order in orders:
            if self._risk_manager.validate(order, account):
                self._broker.submit_order(order)

        _ = self._broker.get_account()
