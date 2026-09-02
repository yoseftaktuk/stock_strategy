# Momentum Trader

An algorithmic trading system for US stocks based on a momentum strategy. This project follows Clean Architecture principles, separating domain logic from infrastructure so the same strategy runs in backtest, paper, and live modes.

## Architecture

The system is organized into layers with strict dependency rules:

```
Domain → Strategy → Application → Infrastructure
```

- **Domain**: Pure business objects (stocks, orders, positions, signals). No external dependencies.
- **Strategy**: Trading logic abstractions. Depends only on domain models.
- **Application**: Orchestration services (rebalance, orders, portfolio). Coordinates strategy and infrastructure.
- **Infrastructure**: Broker, data providers, database, backtest engine. Implements interfaces defined by inner layers.

Business logic must not depend on infrastructure. The strategy never imports IBKR, SQLAlchemy, or HTTP clients.

## Project Structure

```
app/
├── domain/          # Pure domain models and enums
├── strategy/        # Strategy abstractions and momentum strategy
├── application/     # Orchestration services
├── broker/          # Broker interface and implementations
├── data/            # Market data providers and service
├── risk/            # Risk management and kill switch
├── database/        # SQLAlchemy ORM and repositories
├── backtest/        # Backtest engine and metrics
├── universe/        # Point-in-time index membership (S&P 500)
└── main.py          # Composition root / bootstrap

tests/
├── unit/
├── integration/
└── backtest/

data/raw/            # Immutable source CSVs (never modified by the pipeline)
data/processed/      # Reserved for optional exported snapshots (PostgreSQL is the processed store)
migrations/        # Alembic database migrations
scripts/             # Utility scripts
docker/              # Docker helper files
```

## Trading Modes

| Mode | Broker | Description |
|------|--------|-------------|
| `BACKTEST` | `SimulatedBroker` | Historical simulation (default) |
| `PAPER` | `IBKRBroker` | Paper trading via IB Gateway |
| `LIVE` | `IBKRBroker` | Live trading via IB Gateway |

Configure via `TRADING_MODE` environment variable. Default is `BACKTEST`.

## Backtest → Paper → Live Workflow

1. **Backtest**: Develop and validate the strategy using historical data and `SimulatedBroker`.
2. **Paper**: Connect to IB Gateway in paper mode to validate execution and reconciliation.
3. **Live**: Deploy the same strategy code with live credentials and `IBKRBroker`.

The strategy code remains unchanged across all three modes. Only the broker and data provider implementations differ.

## Historical Market Data

The pipeline loads, validates, and stores daily OHLCV bars. Strategy and backtest code consume **PostgreSQL** via `MarketDataService.get_history()`, not CSV files directly.

| Path | Role |
|------|------|
| `data/raw/` | Normalized CSV cache / local source files. The historical provider may refresh these after a successful download. |
| PostgreSQL `market_bars` | Canonical processed history used for retrieval. |
| `data/processed/` | Reserved for optional future exports. Unused in this phase. |

Configure the provider with:

```
DATA_PROVIDER=CSV
CSV_DATA_PATH=data/raw
MARKET_DATA_INSERT_BATCH_SIZE=2000
```

Supported providers:

| Value | Behavior |
|-------|----------|
| `CSV` | Read local files under `CSV_DATA_PATH` (default; offline). |
| `HISTORICAL` | Download daily OHLCV via yfinance (free, no API key), write CSV cache, then import. |
| `IBKR` | Stub only — does not open a broker connection. |

**Limitation:** Downloading AAPL/MSFT does not make a backtest survivorship-bias-free. Historical index membership is a separate universe layer; see [Point-in-Time Universe](#point-in-time-universe).

### CSV format

Required columns:

```
symbol,timestamp,open,high,low,close,adjusted_close,volume
```

Example:

```
symbol,timestamp,open,high,low,close,adjusted_close,volume
AAPL,2025-01-02T14:30:00+00:00,248.93,249.10,241.82,243.85,243.85,55740700
```

File naming under `CSV_DATA_PATH`: `{SYMBOL}.csv` or `{symbol}_daily.csv` (case-insensitive). Rows are also filtered by the `symbol` column. Timestamps must be timezone-aware. `close` and `adjusted_close` are stored separately; empty `adjusted_close` is stored as SQL `NULL`. The pipeline does not forward-fill, interpolate, or otherwise fabricate prices.

Date range convention for import CLIs and providers: **inclusive** on both `--start` and `--end`.

### Import CLI

```bash
source .venv/bin/activate

# Offline CSV import (default provider)
python scripts/import_market_data.py --provider csv --symbol AAPL --symbol MSFT --start 2014-01-01 --end 2025-12-31

# Download via yfinance, cache to data/raw, upsert into PostgreSQL
python scripts/import_market_data.py --provider historical --symbol AAPL --symbol MSFT --start 2014-01-01 --end 2025-12-31

# Historical PIT S&P 500 constituents (warm-up before --start is added automatically)
python scripts/import_market_data.py --provider historical --universe historical_sp500 --start 2015-01-01 --end 2025-12-31

# Coverage diagnostic
python scripts/report_market_data.py --symbol AAPL --symbol MSFT --start 2014-01-01 --end 2025-12-31
python scripts/report_market_data.py --universe historical_sp500 --start 2015-01-01 --end 2025-12-31
```

Repeat `--symbol` to import multiple tickers. `--symbol` wins if both `--symbol` and `--universe` are passed. Each symbol is imported in its own database transaction. Re-running the same import is idempotent: existing `(stock_id, timestamp)` rows are not duplicated. CSV caches under `data/raw/{SYMBOL}.csv` are reused when they already cover the requested window (or when only the tail is short, typical of delisted names). Cache files are merged on write so a later import never shrinks a longer series.

`--universe historical_sp500` loads unique PIT members overlapping `[start, end]` from PostgreSQL (not today's Wikipedia list). Fetch start is extended by the same warm-up buffer the backtest uses (`lookback_days * 2 + 40` calendar days) so Momentum has 252 lookback sessions. Explicit `--symbol` imports still use `--start` unchanged.

Long-range **explicit-symbol** imports fail if only a handful of rows are obtained (quality gate). Universe imports persist valid short series (delisted / late IPO) and report them as incomplete rather than failing the whole run. Tiny sample fixtures under `data/raw/` are for unit tests / smoke checks only.

Yahoo Finance will not have every historical ticker. Failures and empty downloads are reported per symbol; membership is not removed. Do not assume full S&P 500 price coverage.

### Streamlit dashboard

After PostgreSQL is running and history is imported, open the backtest UI:

```bash
source .venv/bin/activate
streamlit run app/ui/dashboard.py
```

Choose start/end dates, a universe, and symbols (when using imported price files), then **Run backtest**. The membership cache `data/raw/sp500_historical.csv` is not a ticker; use **Historical S&P 500 (point-in-time)** instead.

The CLI is unchanged:

```bash
python scripts/run_backtest.py --start 2015-01-01 --end 2025-12-31 --capital 100000 --symbol AAPL --symbol MSFT
```

Named universes (after importing historical constituents):

```bash
python scripts/run_backtest.py --start 2015-01-01 --end 2025-12-31 --capital 100000 --universe historical_sp500
python scripts/run_backtest.py --start 2015-01-01 --end 2025-12-31 --capital 100000 --universe current
python scripts/run_backtest.py --start 2015-01-01 --end 2025-12-31 --capital 100000 --universe historical_sp500 --verbose
```

`--symbol` still wins when both `--symbol` and `--universe` are passed. Default remains explicit symbols / CSV files (not `historical_sp500`) so existing AAPL/MSFT runs stay unchanged.

`--universe current` is allowed for comparison but is marked **survivorship-biased** for historical windows. `--verbose` prints per-rebalance diagnostics (universe members, missing prices, insufficient history, filters, selected). Do not treat a full S&P 500 run as valid research until historical prices exist for the point-in-time members.

### Execution export versus market-data CSV

`data/raw/{SYMBOL}.csv` is **market data** (OHLCV), not trades:

```
symbol,timestamp,open,high,low,close,adjusted_close,volume
```

Backtest execution is a separate export (`--export-dir DIR` or Streamlit download buttons), produced by `app/backtest/export.py` from `BacktestResult`:

| File | Meaning |
|------|---------|
| `fills.csv` | Successful executions (fill count is `number_of_trades`) |
| `orders.csv` | Order intents, including rejected orders |
| `equity_curve.csv` | Daily cash / equity / return / drawdown |

There is no Trade domain type. Fills are not written into the market-data CSV cache.

## Point-in-Time Universe

The universe layer answers **which securities were eligible index members** on a date. Market data answers **what prices exist**. A name can be a historical constituent with no local prices; that is valid and must be reported, not dropped from the universe.

This is a **survivorship-aware**, **point-in-time** membership store. Using it makes S&P 500 research **survivorship-bias-controlled**. It does **not** make the whole backtest bias-free.

### Import (network only here)

```bash
python scripts/import_sp500_universe.py
python scripts/import_sp500_universe.py --source-file data/raw/sp500_historical.csv
```

Import downloads the public [fja05680/sp500](https://github.com/fja05680/sp500) reconstruction, converts change-date snapshots into `[start_date, end_date)` intervals, and upserts them into PostgreSQL. Re-running the import is idempotent. Backtests do **not** download universe data.

### Query

```bash
python scripts/report_sp500_universe.py --as-of 2015-01-02
python scripts/report_sp500_universe.py --as-of 2020-01-02
python scripts/report_sp500_universe.py --as-of 2025-01-02
```

`universe.get_symbols(as_of)` returns `sorted(unique(symbols))` for members with `start_date <= as_of` and (`end_date IS NULL` or `as_of < end_date`).

At every monthly rebalance the backtest engine calls `universe.get_symbols(rebalance_date)` independently. The rebalance date is the **first trading session of each month** after warmup (`lookback_days + 1` sessions). That session is the signal/decision date; orders still execute at the **next session open**. The universe query uses the signal date, not a calendar month-end and not a one-time snapshot at the start of the backtest.

Backtest flags:

| Flag | Behavior |
|------|----------|
| `--universe historical_sp500` | Point-in-time constituents at each monthly rebalance |
| `--universe current` | Currently active members on every date (**survivorship-biased**) |
| `--verbose` | Print per-rebalance membership and filter diagnostics |

`--universe current` reports:

```
Universe:
current
CURRENT UNIVERSE WARNING: SURVIVORSHIP-BIASED FOR HISTORICAL BACKTESTING
```

`--universe historical_sp500` reports `Historical S&P 500 Point-in-Time`. Missing market data and insufficient history are reported separately; constituents are not dropped from the historical universe because prices are absent.

This pipeline is **survivorship-aware** and **point-in-time universe aware**. Index membership is **survivorship-bias-controlled**. It is **not** completely bias-free.

### Source limitations

The fja05680/sp500 dataset is **not** an official S&P Dow Jones Indices feed. Remaining limitations include:

- Historical membership accuracy depends on that public reconstruction.
- Ticker changes are not solved; source tickers are stored after stripping dataset-only `-YYYYMM` suffixes. Share-class marks such as `BRK.B` are not mapped to Yahoo `BRK-B`. No unsupported ticker substitutions are performed.
- Delisted, acquired, or renamed securities often have no Yahoo history under the source ticker. Unavailable prices are recorded as missing/failed market data, not replaced with a current ticker. A future Security Master / delisted-price source may be required.
- Corporate actions still require careful price handling (`adjusted_close`). Missing adjusted close is reported; Close is not silently substituted.
- Market-data coverage is independent of PIT membership. Incomplete Yahoo coverage is **Partial Historical Market Data Coverage**, not a universe bug, and is **not** a full research-quality S&P 500 backtest until validation proves otherwise.
- Execution, slippage, and commission assumptions remain those of `SimulatedBroker`.
- Data snooping and research-selection bias are out of scope for this layer.
- A survivorship-aware universe does not automatically make the backtest free of look-ahead, liquidity, or corporate-action bias.

Universe import does **not** download S&P 500 market data and does **not** fall back to today's constituent list. Backtests load prices from PostgreSQL (or injected fixtures) and do **not** call yfinance.

## Technology Stack

- Python 3.12+
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic / Pydantic Settings
- pandas
- Streamlit / Plotly (backtest dashboard)
- pytest
- Docker / Docker Compose
- Interactive Brokers TWS API / IB Gateway (future integration)

## Local Development Setup

1. Clone the repository and create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate   # must use "source", not run directly
pip install -r requirements.txt
pip install -e .
```

**Important:** Activate the venv with `source .venv/bin/activate` (note the `source` prefix). Running `.venv/bin/activate` alone will fail with `permission denied` — that script is meant to be sourced into your shell, not executed.

Always use the venv before `alembic`, `pytest -m integration`, etc. System Python will fail with `ModuleNotFoundError: No module named 'psycopg2'`.

2. Copy environment variables:

```bash
cp .env.example .env
```

3. Start PostgreSQL (default host port **5433** to avoid conflicts with other local Postgres containers on 5432):

```bash
docker compose up postgres -d
# or: scripts/dev.sh postgres
```

4. Run migrations and tests:

```bash
source .venv/bin/activate
alembic upgrade head
pytest -m unit -v
pytest -m integration -v

# Convenience wrapper (activates venv + sets defaults):
chmod +x scripts/dev.sh
scripts/dev.sh test
```

## Docker Setup

Build and start all services:

```bash
docker compose up --build
```

Services:

- **trading-engine**: Python application container
- **postgres**: PostgreSQL 16 database
- **ib-gateway**: Placeholder for future IB Gateway integration

## PostgreSQL Setup

PostgreSQL is configured via environment variables in `.env`:

```
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=momentum_trader
POSTGRES_USER=momentum
POSTGRES_PASSWORD=change_me
POSTGRES_TEST_DB=momentum_trader_test
```

Run Alembic migrations after the database is available:

```bash
alembic upgrade head
```

For integration tests, start PostgreSQL and create the test database:

```bash
source .venv/bin/activate
docker compose up postgres -d   # listens on localhost:5433 by default
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5433
export POSTGRES_TEST_DB=momentum_trader_test
pytest -m integration -v
```

## Running Tests

```bash
# Unit tests only
pytest -m unit -v

# Integration tests (requires PostgreSQL + activated venv)
source .venv/bin/activate
docker compose up postgres -d
export POSTGRES_HOST=localhost POSTGRES_PORT=5433
pytest -m integration -v

# Backtest tests
pytest tests/backtest/ -v

# Full suite
pytest tests/ -v
```

## Future IBKR Integration

The `app/broker/ibkr/` package contains placeholder classes for future Interactive Brokers integration:

- `IBKRClient`: Encapsulates TWS API / IB Gateway communication
- `IBKRBroker`: Implements the `Broker` interface
- `orders.py`, `positions.py`, `market_data.py`: IBKR-specific mapping helpers

IBKR dependencies (`ibapi`, `ib_insync`, etc.) are intentionally omitted until the integration phase. All IBKR methods currently raise `NotImplementedError` to prevent accidental order submission.
