from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timezone
from decimal import Decimal
import logging

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.diagnostics import (
    CURRENT_UNIVERSE_WARNING,
    DataCoverageSnapshot,
    RebalanceDiagnostics,
    historical_market_data_coverage_warning,
    is_current_universe,
)
from app.backtest.metrics import MetricsCalculator
from app.backtest.result import BacktestResult
from app.broker.interface import BacktestBroker
from app.domain.models.equity import EquityPoint
from app.domain.models.market_bar import MarketBar
from app.domain.models.order import Order
from app.domain.models.position import Position
from app.domain.models.target import TargetPortfolio
from app.risk.risk_manager import RiskManager
from app.strategy.base import Strategy
from app.universe.coverage import missing_market_data_symbols
from app.universe.factory import HISTORICAL_SP500
from app.universe.interface import UniverseProvider

logger = logging.getLogger(__name__)
UTC = timezone.utc


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        broker: BacktestBroker,
        portfolio_service: PortfolioService,
        order_service: OrderService,
        risk_manager: RiskManager,
        config: BacktestConfig,
        metrics_calculator: MetricsCalculator | None = None,
        universe_provider: UniverseProvider | None = None,
    ) -> None:
        self._strategy = strategy
        self._broker = broker
        self._portfolio_service = portfolio_service
        self._order_service = order_service
        self._risk_manager = risk_manager
        self._config = config
        self._metrics = metrics_calculator or MetricsCalculator()
        self._universe_provider = universe_provider

    def run(
        self,
        start: date | None = None,
        end: date | None = None,
        market_data: Mapping[str, Sequence[MarketBar]] | None = None,
    ) -> BacktestResult:
        start_date = start or self._config.start_date
        end_date = end or self._config.end_date
        if market_data is None:
            raise ValueError("market_data is required; load history before running the engine")

        trading_dates, bars_by_date = _build_calendar(market_data, start_date, end_date)
        warmup = self._warmup_sessions()
        rebalance_dates = _monthly_rebalance_dates(trading_dates, warmup)
        warnings: list[str] = []
        submitted: list[Order] = []
        pending_target: TargetPortfolio | None = None
        missing_by_rebalance: list[tuple[date, list[str]]] = []
        universe_sizes: list[int] = []
        universe_member_symbols: set[str] = set()
        insufficient_history_symbols: set[str] = set()
        rebalance_diagnostics: list[RebalanceDiagnostics] = []
        if is_current_universe(self._config.universe_kind):
            warnings.append(CURRENT_UNIVERSE_WARNING)
        if not trading_dates:
            warnings.append(
                f"No trading days between {start_date.isoformat()} and {end_date.isoformat()}. "
                "Loaded bars are empty or outside the requested period."
            )
        elif not rebalance_dates:
            warnings.append(
                "No monthly rebalance ran: need "
                f"{warmup} warmup sessions, but the calendar has {len(trading_dates)} "
                f"trading days ({trading_dates[0].isoformat()} to {trading_dates[-1].isoformat()}). "
                "Import a longer daily series before the start date."
            )

        if not self._broker.is_connected():
            self._broker.connect()

        equity_curve: list[EquityPoint] = []
        peak_equity = self._config.initial_capital
        previous_equity: Decimal | None = None

        for session in trading_dates:
            day_bars = bars_by_date[session]
            opens = {symbol: bar.open for symbol, bar in day_bars.items()}
            closes = {symbol: bar.close for symbol, bar in day_bars.items()}
            session_time = _session_timestamp(session, day_bars)

            if pending_target is not None:
                missing = _missing_execution_symbols(pending_target, self._broker.get_positions(), opens)
                for symbol in missing:
                    message = f"missing open for execution symbol={symbol} date={session.isoformat()}"
                    logger.warning(message)
                    warnings.append(message)
                self._broker.set_market_prices(opens, session_time)
                self._broker.mark_to_market(opens)
                orders = self._order_service.create_orders_from_targets(
                    self._broker.get_account(),
                    pending_target,
                    opens,
                    min_trade_value=self._config.min_trade_value,
                    as_of=session,
                )
                for order in orders:
                    account = self._broker.get_account()
                    if self._risk_manager.validate(order, account):
                        submitted.append(self._broker.submit_order(order))
                    else:
                        submitted.append(order)
                pending_target = None

            self._broker.mark_to_market(closes)
            marked = _mark_missing_closes(self._broker, closes, session, warnings)
            if marked:
                self._broker.mark_to_market(marked)

            account = self._broker.get_account()
            equity = account.equity
            if previous_equity is None or previous_equity == 0:
                daily_return = Decimal("0")
            else:
                daily_return = equity / previous_equity - 1
            if equity > peak_equity:
                peak_equity = equity
            drawdown = equity / peak_equity - 1 if peak_equity > 0 else Decimal("0")
            equity_curve.append(
                EquityPoint(
                    date=session,
                    equity=equity,
                    cash=account.cash,
                    returns=daily_return,
                    drawdown=drawdown,
                )
            )
            previous_equity = equity

            if session in rebalance_dates:
                signal_data, missing, eligible = _universe_market_data(
                    market_data,
                    session,
                    self._universe_provider,
                )
                universe_members = len(eligible)
                universe_member_symbols.update(eligible)
                if missing:
                    missing_by_rebalance.append((session, missing))
                universe_sizes.append(universe_members)
                evaluation = self._strategy.evaluate(signal_data, session)
                signals = evaluation.signals
                pending_target = self._portfolio_service.build_target_portfolio(signals)
                counts = evaluation.counts
                if counts.insufficient_history:
                    lookback = getattr(getattr(self._strategy, "config", None), "lookback_days", None)
                    need = lookback + 1 if isinstance(lookback, int) and lookback > 0 else None
                    if need is not None:
                        for symbol, bars in signal_data.items():
                            sliced = [bar for bar in bars if bar.timestamp.date() <= session]
                            if len(sliced) < need:
                                insufficient_history_symbols.add(symbol)
                rebalance_diagnostics.append(
                    RebalanceDiagnostics(
                        as_of=session,
                        universe_members=universe_members,
                        missing_market_data=len(missing),
                        insufficient_history=counts.insufficient_history,
                        failed_price_filter=counts.failed_price_filter,
                        failed_liquidity_filter=counts.failed_liquidity_filter,
                        momentum_eligible=counts.momentum_eligible,
                        selected=counts.selected,
                    )
                )
                logger.info(
                    "Rebalance queued as_of=%s members=%s missing=%s eligible=%s selected=%s",
                    session.isoformat(),
                    universe_members,
                    len(missing),
                    counts.momentum_eligible,
                    len(signals),
                )

        metrics = self._metrics.calculate(
            equity_curve,
            self._config.initial_capital,
            risk_free_rate=self._config.risk_free_rate,
            start=start_date,
            end=end_date,
        )
        final_equity = equity_curve[-1].equity if equity_curve else self._config.initial_capital
        spy_return = _spy_buy_hold_return(bars_by_date, trading_dates)
        fills = self._broker.get_fills()
        warnings.extend(_summarize_missing_market_data(missing_by_rebalance, market_data))
        priced_set = {symbol for symbol, bars in market_data.items() if bars}
        priced_symbols = tuple(sorted(priced_set))
        missing_price_count = len({symbol for _as_of, missing in missing_by_rebalance for symbol in missing})
        universe_member_peak = max(universe_sizes) if universe_sizes else None
        last_diag = rebalance_diagnostics[-1] if rebalance_diagnostics else None
        coverage_warning = None
        if self._config.universe_kind == HISTORICAL_SP500:
            coverage_warning = historical_market_data_coverage_warning(missing_price_count)
            if coverage_warning:
                warnings.append(coverage_warning)
        member_count = len(universe_member_symbols) if universe_member_symbols else len(market_data)
        member_priced = priced_set & universe_member_symbols if universe_member_symbols else priced_set
        coverage = DataCoverageSnapshot(
            universe_member_peak=universe_member_peak,
            universe_members=member_count,
            market_data_available=len(member_priced - insufficient_history_symbols),
            missing_market_data=missing_price_count,
            insufficient_history=len(insufficient_history_symbols),
            momentum_eligible=last_diag.momentum_eligible if last_diag else 0,
            selected=last_diag.selected if last_diag else 0,
            warning=coverage_warning,
        )

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self._config.initial_capital,
            final_equity=final_equity,
            total_return=metrics.total_return,
            annualized_return=metrics.annualized_return,
            volatility=metrics.volatility,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown,
            number_of_trades=len(fills),
            winning_trades=self._broker.winning_trades,
            losing_trades=self._broker.losing_trades,
            total_commission=self._broker.total_commission,
            total_slippage=self._broker.total_slippage,
            equity_curve=tuple(equity_curve),
            fills=tuple(fills),
            orders=tuple(submitted),
            spy_buy_hold_return=spy_return,
            warnings=tuple(warnings),
            priced_symbols=priced_symbols,
            universe_member_peak=universe_member_peak,
            missing_price_count=missing_price_count,
            universe_kind=self._config.universe_kind,
            rebalance_diagnostics=tuple(rebalance_diagnostics),
            coverage=coverage,
        )

    def _warmup_sessions(self) -> int:
        strategy_config = getattr(self._strategy, "config", None)
        lookback = getattr(strategy_config, "lookback_days", None)
        if isinstance(lookback, int) and lookback > 0:
            return lookback + 1
        return self._config.warmup_sessions


def _universe_market_data(
    market_data: Mapping[str, Sequence[MarketBar]],
    as_of: date,
    universe_provider: UniverseProvider | None,
) -> tuple[Mapping[str, Sequence[MarketBar]], list[str], list[str]]:
    if universe_provider is None:
        eligible = sorted(market_data)
    else:
        eligible = universe_provider.get_symbols(as_of)
    missing = missing_market_data_symbols(eligible, market_data)
    filtered = {
        symbol: bars
        for symbol in eligible
        if (bars := market_data.get(symbol))
    }
    return filtered, missing, eligible


def _summarize_missing_market_data(
    missing_by_rebalance: Sequence[tuple[date, Sequence[str]]],
    market_data: Mapping[str, Sequence[MarketBar]],
) -> list[str]:
    if not missing_by_rebalance:
        return []
    unique: set[str] = set()
    peak = 0
    for _as_of, missing in missing_by_rebalance:
        unique.update(missing)
        peak = max(peak, len(missing))
    priced = sorted(symbol for symbol, bars in market_data.items() if bars)
    preview = ", ".join(sorted(unique)[:20])
    return [
        "Missing market data: "
        f"{len(unique)} unique constituents have no prices "
        f"(peak {peak} missing on a rebalance date, "
        f"{len(missing_by_rebalance)} dates). "
        f"Prices loaded for {len(priced)} symbol(s). "
        "Universe membership was not dropped. "
        f"Sample missing: {preview}."
    ]


def _build_calendar(
    market_data: Mapping[str, Sequence[MarketBar]],
    start: date,
    end: date,
) -> tuple[list[date], dict[date, dict[str, MarketBar]]]:
    bars_by_date: dict[date, dict[str, MarketBar]] = {}
    for bars in market_data.values():
        for bar in bars:
            session = bar.timestamp.date()
            if session < start or session > end:
                continue
            bars_by_date.setdefault(session, {})[bar.symbol] = bar
    return sorted(bars_by_date), bars_by_date


def _monthly_rebalance_dates(trading_dates: Sequence[date], warmup_sessions: int) -> set[date]:
    selected: set[date] = set()
    for index, session in enumerate(trading_dates):
        if index + 1 < warmup_sessions:
            continue
        is_month_start = index == 0 or (
            session.year,
            session.month,
        ) != (trading_dates[index - 1].year, trading_dates[index - 1].month)
        if is_month_start:
            selected.add(session)
    return selected


def _session_timestamp(session: date, day_bars: Mapping[str, MarketBar]) -> datetime:
    timestamps = [bar.timestamp for bar in day_bars.values() if bar.timestamp.tzinfo is not None]
    if timestamps:
        return min(timestamps).replace(hour=9, minute=30, second=0, microsecond=0)
    return datetime.combine(session, time(9, 30), tzinfo=UTC)


def _missing_execution_symbols(
    target: TargetPortfolio,
    positions: Sequence[Position],
    opens: Mapping[str, Decimal],
) -> list[str]:
    needed = {item.symbol for item in target.positions}
    needed.update(position.symbol for position in positions)
    return sorted(symbol for symbol in needed if symbol not in opens)


def _mark_missing_closes(
    broker: BacktestBroker,
    closes: Mapping[str, Decimal],
    session: date,
    warnings: list[str],
) -> dict[str, Decimal] | None:
    merged = dict(closes)
    missing = False
    for position in broker.get_positions():
        if position.symbol not in merged:
            message = (
                f"missing close for mark-to-market symbol={position.symbol} "
                f"date={session.isoformat()}; holding last price"
            )
            logger.warning(message)
            warnings.append(message)
            merged[position.symbol] = position.market_price
            missing = True
    return merged if missing else None


def _spy_buy_hold_return(
    bars_by_date: Mapping[date, Mapping[str, MarketBar]],
    trading_dates: Sequence[date],
) -> float | None:
    closes: list[Decimal] = []
    for session in trading_dates:
        bar = bars_by_date[session].get("SPY")
        if bar is not None:
            closes.append(bar.close)
    if len(closes) < 2 or closes[0] == 0:
        return None
    return float(closes[-1] / closes[0] - 1)
