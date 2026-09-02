# Historical S&P 500 / Point-in-Time Universe Architecture Audit

This document describes how the Historical S&P 500 constituents, point-in-time
(PIT) universe, market-data selection, backtest, fills, CSV surfaces, and
Streamlit dashboard actually work. It records **current semantics**. It does not
claim the pipeline is research-ready.

Source of membership: public reconstruction [fja05680/sp500](https://github.com/fja05680/sp500),
**not** an official S&P Dow Jones Indices feed. Official index accuracy is
**UNCERTAIN**.

## End-to-end flow

```
fja05680 CSV snapshots (date, tickers)
  → SP500HistoricalSource.parse_snapshots
  → snapshots_to_intervals  [start_date, end_date)
  → validate_memberships (duplicates + overlaps)
  → PostgreSQL sp500_constituent_memberships
  → UniverseService.snapshot_provider → InMemoryUniverseProvider
  → BacktestEngine on each monthly rebalance:
       eligible = universe.get_symbols(rebalance_date)
       strategy sees only members that also have local prices
  → OrderService (sells then buys)
  → SimulatedBroker (one fill or reject; no partial fills)
  → BacktestResult (authoritative metrics)
  → Streamlit presentation.py / optional fills.csv + orders.csv export
```

There is no `get_universe` / `constituents_as_of` API. The canonical query is
`UniverseProvider.get_symbols(as_of)`.

---

## 1. Historical S&P 500 constituent implementation

| Piece | Location |
|-------|----------|
| Source adapter | `app/universe/providers/sp500.py` (`SP500HistoricalSource`) |
| Cached CSV | `data/raw/sp500_historical.csv` |
| Import CLI | `scripts/import_sp500_universe.py` |
| Domain interval | `app/universe/models.py` (`ConstituentMembership`) |
| Persistence | `app/database/models.py` (`SP500ConstituentMembershipModel`) |
| Repository | `app/database/repositories/sp500_constituents.py` |

Each source row is a **change-date snapshot**: columns `date`, `tickers`
(comma-separated). `snapshots_to_intervals` converts ordered snapshots into
half-open membership intervals. A ticker that leaves gets `end_date = change_date`
(exclusive). A ticker that enters gets `start_date = change_date` (inclusive).
Re-entries become **separate** intervals and are never merged.

Import is the only path that may hit the network. Backtests and the strategy
must not import `SP500HistoricalSource` (enforced by
`tests/unit/universe/test_universe_architecture.py` and
`tests/backtest/test_backtest_architecture.py`).

## 2. Point-in-time universe implementation

| Kind | Class | Behavior |
|------|-------|----------|
| `historical_sp500` | `HistoricalSP500UniverseProvider` | `get_memberships_as_of(as_of)` then unique sorted symbols |
| `current` | `CurrentSP500UniverseProvider` | Ignores `as_of`; returns symbols with `end_date is None` (**survivorship-biased**) |
| Snapshot / tests | `InMemoryUniverseProvider` | Same `contains(as_of)` rule, or `current_only=True` |

`UniverseService.get_symbols` delegates to the provider.
`UniverseService.symbols_overlapping_window(start, end)` returns unique symbols
whose intervals overlap the inclusive `[start, end]` window (used to **load
prices**, not to decide eligibility on a rebalance date).

`UniverseService.snapshot_provider` copies all DB memberships into memory so the
engine performs no database I/O during the run.

## 3. Membership date representation

Half-open: **`start_date <= as_of < end_date`**.

`end_date is None` means still active.

`ConstituentMembership.contains` and the SQL in `get_memberships_as_of` implement
the same rule (`start_date <= as_of` AND (`end_date IS NULL` OR `as_of < end_date`)).

Adjacent intervals that share a boundary (end = next start) do **not** overlap.
`start_date >= end_date` is rejected at domain construction
(`DomainValidationError`).

## 4. Symbol / ticker normalization

Two layers:

1. `normalize_symbol` (`app/data/validation.py`): `strip().upper()`.
2. `normalize_constituent_symbol` (`app/universe/providers/sp500.py`): also
   strips dataset-only `-YYYYMM` removal suffixes (`AAL-199702` → `AAL`).
   Share-class punctuation is preserved (`BRK.B` stays `BRK.B`; not mapped to
   Yahoo `BRK-B`).

`ConstituentMembership.__post_init__` runs `normalize_symbol` again.

## 5. Ticker change handling

**Not solved.** There is no Security Master, rename table, or successor mapping.
Source tickers are stored after suffix strip only. A rename that changes the
ticker string appears as a remove of the old symbol and an add of the new one
**if** the source snapshots encode it that way. Yahoo often remaps an entire
price history onto the **current** ticker (for example SQ history served as
`XYZ`). The membership store does not know that those strings are the same
issuer.

## 6. Delisted companies handling

Delisting / removal = membership `end_date` set. After that date the name is
not returned by PIT `get_symbols`. Price availability is independent:
`missing_market_data_symbols` reports gaps; membership is not dropped because
Yahoo has no series. There is no remapping of a delisted ticker to a successor.
Ticker **recycling** (a new company reuse of an old ticker) is not detected at
import time.

## 7. Market-data universe construction

`scripts/import_market_data.py --universe historical_sp500` resolves symbols via
`UniverseService.symbols_overlapping_window(start, end)` (plus a Momentum warmup
buffer). That is the union of names that were members **at any time** in the
window — a superset of any single rebalance date.

Local CSVs live under `data/raw/{SYMBOL}.csv`. `discover_csv_symbols` skips
`sp500_historical.csv` so the membership cache is not treated as a ticker.
PostgreSQL `market_bars` is the canonical store the backtest reads.

## 8. Backtest universe construction

`run_momentum_backtest` (`app/backtest/runner.py`):

- Explicit `--symbol` wins over `--universe`.
- `historical_sp500`: snapshot all memberships; load prices for
  `symbols_overlapping_window(start, end)`.
- `current`: snapshot with `current_only=True`; load prices for currently
  active members only.
- Default (no named universe): CSV stems / `Settings.universe` (not PIT).

The engine still filters **per rebalance date** via `get_symbols(as_of)`.
Loading a superset of prices does not put non-members into the strategy.

## 9. Rebalance-date universe construction

Monthly rebalances = **first trading session of each month** after warmup
(`lookback_days + 1` sessions). See `_monthly_rebalance_dates` in
`app/backtest/engine.py`.

On each rebalance session `_universe_market_data`:

1. `eligible = universe_provider.get_symbols(as_of)` (or all priced symbols if
   no provider).
2. `missing` = eligible names with no bars.
3. Strategy input = eligible names that have bars.

The universe as-of is the **signal/rebalance date**, not month-end and not a
one-time snapshot at backtest start. Orders execute at the **next session open**.

## 10. Order generation

`OrderService.create_orders_from_targets` (`app/application/order_service.py`):

- Diff target dollar weight vs current; skip if `|Δvalue| < min_trade_value`
  (default `$100`).
- Size with slippage-adjusted prices.
- **Sells first**, then cash-constrained buys.
- `client_order_id` = `{YYYY-MM-DD}-{sequence:04d}`.
- Side is stored on `Order.side` (`BUY` / `SELL`).
- Risk-rejected orders remain `CREATED` and are recorded on `BacktestResult.orders`
  but produce no fill.

## 11. Fill generation

`SimulatedBroker.submit_order` (`app/broker/simulated.py`):

- Immediate fill at slipped price if cash/shares allow; else `REJECTED`.
- **One fill per successful order.** Partial fills are not implemented
  (`PARTIALLY_FILLED` exists on the enum but is unused here).
- Domain `Fill` has `order_id` (= `client_order_id`), symbol, quantity, price,
  commission, timestamp. Side is **not** stored on `Fill`; join to `Order`.
- Buy cash: `trade_value + commission`. Sell cash: `trade_value - commission`.

## 12. Trade accounting

There is **no** Trade domain or table. UI metric **Trades** =
`BacktestResult.number_of_trades` = `len(fills)`.

`winning_trades` / `losing_trades` increment only on **SELL** vs average cost
(breakeven sells count as neither). Therefore
`winning_trades + losing_trades` is typically **less than** `number_of_trades`
(buys plus flat sells).

## 13. Commission calculation

`commission_on(trade_value, commission_rate)` =
`trade_value * commission_rate` when both are positive.

Default `BacktestConfig.commission_rate = 0.0005` (5 bps of slipped fill value).
`BacktestResult.total_commission` is the broker’s running sum of fill
commissions. Streamlit displays that field; it must not recompute it.

## 14. Slippage calculation

`apply_slippage`: BUY `market * (1 + bps/10000)`; SELL `market * (1 - bps/10000)`.
Default `10` bps.

Broker total slippage = `sum(|fill_price - market_price| * quantity)`.
Per-fill slippage is recorded on `Fill.slippage` at fill time (same formula).
It is not fabricated after the fact.

## 15. CSV export

**Originally** there was no dedicated trade CSV. Streamlit’s dataframe chrome
could download `fills_table` with columns `Time, Symbol, Quantity, Price,
Commission` — fills, not round-trips, and **without side**.

**Audit addition:** `app/backtest/export.py` writes separate files from the same
`BacktestResult`:

| File | Rows | Meaning |
|------|------|---------|
| `fills.csv` | Successful executions | Join to orders for `side`; includes `order_id`, `gross_value`, `commission`, `slippage`, `net_value`, optional `cash` / `position_quantity` |
| `orders.csv` | All generated orders | Includes rejected / unsubmitted; has `side` and `status` |

There is no `trades.csv` because there is no Trade type. **Trades = fills.**

CLI `scripts/run_backtest.py --export-dir DIR` writes those files.
Streamlit offers the same downloads from session state.

Optional universe audit CSVs (off by default for the detail file):

| File | When |
|------|------|
| `audit/universe_summary.csv` | `--universe-audit` |
| `audit/universe_by_rebalance.csv` | `--universe-audit-detail` (optionally `--universe-audit-changes-only`) |

## 16. Streamlit dashboard data source

`app/ui/dashboard.py` calls `run_momentum_backtest` and stores `BacktestResult`
in `st.session_state["backtest_result"]`. There is no DB persistence of backtest
runs.

`app/ui/presentation.py` formats engine fields only:

| UI metric | Source |
|-----------|--------|
| Total Return | `result.total_return` (`final_equity / initial_capital - 1`) |
| Trades | `result.number_of_trades` (`len(fills)`) |
| Commission | `result.total_commission` |
| Slippage | `result.total_slippage` |
| Coverage / diagnostics | `result.coverage`, `result.rebalance_diagnostics` |

The Trades table is the fills table (now including Side and Order ID). Positions
are not shown as a separate live blotter; equity/cash come from `equity_curve`.

---

## Validation already present (pre-audit)

`validate_memberships` (`app/universe/validation.py`) at import:

- Exact duplicate intervals (non-blocking; unique set is persisted).
- Overlapping intervals (blocking; import aborted).

It does **not** check price-window identity, fixture `source="test-fixture"`
leakage into a production table, or per-rebalance eligibility dumps.

Audit additions live in `app/universe/audit.py` and
`scripts/audit_historical_universe.py`. They **report**; they do not delete
memberships.

## Fixture / test contamination risk

| Symbol / source | Where | Production risk |
|-----------------|-------|-----------------|
| AAA–EEE, ZZZ | `tests/fixtures/universe.py` only | Low for files; no matching price CSVs |
| `source="test-fixture"` | Fixtures | High only if integration tests upsert into a shared production DB |
| `sp500_historical.csv` | `data/raw/` | Mitigated: skipped by CSV symbol discovery |

## Known limitations (not automatically “PASS”)

1. Unofficial membership reconstruction.
2. No ticker-change / recycling Security Master.
3. Yahoo identity of a ticker string can be a different issuer than the
   historical constituent (market-data mismatch, not a PIT query bug).
4. Incomplete local prices → strategy sees a subset of the true PIT universe.
5. `--universe current` is survivorship-biased by design.
6. Corporate actions / adjusted close remain a separate concern.

A passing unit suite proves the **interval algebra and wiring**. It does not
prove the fja05680 file matches official SPDJI membership or that Yahoo bars
are the same economic entity as the historical constituent.
