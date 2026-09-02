from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.application.order_service import OrderService
from app.application.portfolio_service import PortfolioService
from app.backtest.config import BacktestConfig
from app.backtest.data import discover_csv_symbols, load_market_data, max_bar_count
from app.backtest.engine import BacktestEngine
from app.backtest.exceptions import EmptyUniverseError, InsufficientHistoryError
from app.backtest.metrics import MetricsCalculator
from app.backtest.result import BacktestResult
from app.broker.simulated import SimulatedBroker
from app.config.settings import Settings
from app.data.market_data import MarketDataService
from app.data.providers.offline import OfflineMarketDataProvider
from app.database.repositories.market_data import PostgresMarketDataRepository
from app.database.repositories.sp500_constituents import PostgresSP500ConstituentRepository
from app.database.session import ensure_database_available, session_scope
from app.domain.models.market_bar import MarketBar
from app.risk.risk_manager import RiskManager
from app.strategy.config import MomentumConfig
from app.strategy.momentum import MomentumStrategy
from app.universe.factory import CURRENT, create_universe_provider
from app.universe.interface import UniverseProvider
from app.universe.service import UniverseService


def resolve_universe(
    settings: Settings,
    explicit: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return symbols from ``explicit``, else Settings.universe, else CSV files."""
    selected = _normalize_symbols(explicit)
    if selected:
        return selected
    from_settings = _normalize_symbols(settings.universe)
    if from_settings:
        return from_settings
    if settings.data_provider.upper() == "CSV":
        return discover_csv_symbols(Path(settings.csv_data_path))
    return ()


def available_symbols(settings: Settings) -> tuple[str, ...]:
    """Union of Settings.universe and CSV stems under CSV_DATA_PATH."""
    return _normalize_symbols(
        (*settings.universe, *discover_csv_symbols(Path(settings.csv_data_path)))
    )


def ensure_sufficient_history(
    market_data: Mapping[str, Sequence[MarketBar]],
    *,
    lookback_days: int,
    start: date,
    end: date,
    csv_data_path: str,
) -> None:
    need = lookback_days + 1
    loaded = max_bar_count(market_data)
    if loaded < need:
        raise InsufficientHistoryError(
            need=need,
            loaded=loaded,
            lookback_days=lookback_days,
            bar_counts={symbol: len(bars) for symbol, bars in market_data.items()},
            start=start,
            end=end,
            csv_data_path=csv_data_path,
        )


def run_momentum_backtest(
    start: date,
    end: date,
    *,
    capital: Decimal,
    symbols: Sequence[str] | None = None,
    universe: str | None = None,
    settings: Settings | None = None,
) -> BacktestResult:
    """Load history from PostgreSQL and run the monthly momentum backtest.

    Explicit ``symbols`` win over ``universe``. ``historical_sp500`` uses a
    point-in-time membership snapshot already stored in PostgreSQL. ``current``
    uses currently active members for every date and is survivorship-biased.
    """
    resolved_settings = settings or Settings()
    explicit = _normalize_symbols(symbols)
    ensure_database_available(resolved_settings)
    momentum_config = _momentum_config(resolved_settings)
    universe_kind = None if explicit else _normalize_universe_kind(universe)

    universe_provider: UniverseProvider | None = None
    load_symbols = explicit

    with session_scope(resolved_settings) as session:
        if not load_symbols and universe:
            load_symbols, universe_provider = _resolve_named_universe(session, universe, start, end)
        elif not load_symbols:
            load_symbols = resolve_universe(resolved_settings, None)

        if not load_symbols:
            raise EmptyUniverseError(
                "Universe is empty. Pass --symbol, --universe historical_sp500|current, "
                "set UNIVERSE in .env, or add CSV files under "
                f"{resolved_settings.csv_data_path}"
            )

        repository = PostgresMarketDataRepository(
            session,
            batch_size=resolved_settings.market_data_insert_batch_size,
        )
        service = MarketDataService(provider=OfflineMarketDataProvider(), repository=repository)
        market_data = load_market_data(
            service,
            load_symbols,
            start,
            end,
            lookback_days=momentum_config.lookback_days,
        )
        ensure_sufficient_history(
            market_data,
            lookback_days=momentum_config.lookback_days,
            start=start,
            end=end,
            csv_data_path=resolved_settings.csv_data_path,
        )

    engine = _build_engine(
        resolved_settings,
        momentum_config,
        start,
        end,
        capital,
        load_symbols,
        universe_provider=universe_provider,
        universe_kind=universe_kind,
    )
    return engine.run(start, end, market_data=market_data)


def _resolve_named_universe(
    session: Session,
    universe: str,
    start: date,
    end: date,
) -> tuple[tuple[str, ...], UniverseProvider]:
    constituent_repo = PostgresSP500ConstituentRepository(session)
    provider = create_universe_provider(universe, constituent_repo)
    service = UniverseService(constituent_repo, provider=provider)
    current_only = universe.strip().lower() == CURRENT
    snapshot = service.snapshot_provider(current_only=current_only)
    if current_only:
        symbols = tuple(snapshot.get_symbols(end))
    else:
        symbols = tuple(service.symbols_overlapping_window(start, end))
    return symbols, snapshot


def _normalize_universe_kind(universe: str | None) -> str | None:
    if universe is None:
        return None
    return universe.strip().lower() or None


def _normalize_symbols(symbols: Sequence[str] | None) -> tuple[str, ...]:
    seen: list[str] = []
    for raw in symbols or ():
        symbol = str(raw).strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return tuple(seen)


def _momentum_config(settings: Settings) -> MomentumConfig:
    return MomentumConfig(
        lookback_days=settings.momentum_lookback,
        skip_days=settings.momentum_skip,
        top_n=settings.top_n,
        min_price=settings.min_price,
        liquidity_window_days=settings.liquidity_window_days,
        min_dollar_volume=settings.min_dollar_volume,
    )


def _build_engine(
    settings: Settings,
    momentum_config: MomentumConfig,
    start: date,
    end: date,
    capital: Decimal,
    symbols: Sequence[str],
    universe_provider: UniverseProvider | None = None,
    universe_kind: str | None = None,
) -> BacktestEngine:
    slippage_bps = settings.slippage * Decimal("10000")
    backtest_config = BacktestConfig(
        start_date=start,
        end_date=end,
        initial_capital=capital,
        symbols=tuple(symbols),
        warmup_sessions=momentum_config.lookback_days + 1,
        slippage_bps=slippage_bps,
        universe_kind=universe_kind,
    )
    return BacktestEngine(
        strategy=MomentumStrategy(momentum_config),
        broker=SimulatedBroker(
            initial_capital=backtest_config.initial_capital,
            commission_rate=backtest_config.commission_rate,
            slippage_bps=backtest_config.slippage_bps,
        ),
        portfolio_service=PortfolioService(),
        order_service=OrderService(
            commission_rate=backtest_config.commission_rate,
            slippage_bps=backtest_config.slippage_bps,
        ),
        risk_manager=RiskManager(),
        config=backtest_config,
        metrics_calculator=MetricsCalculator(),
        universe_provider=universe_provider,
    )
