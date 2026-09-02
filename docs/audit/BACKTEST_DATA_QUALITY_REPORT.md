# Backtest Data Quality Report

Final integrity audit of the momentum backtest. Architecture facts used as source of truth:

- There is no Trade domain model and no Trade DB model.
- `BacktestResult.number_of_trades = len(fills)`.
- Orders have BUY/SELL side. Fills do not store side; side is joined from Order.
- `data/raw/{SYMBOL}.csv` is market-data OHLCV, not execution data.
- Streamlit stores `BacktestResult` in `session_state`. Backtest results are not persisted in PostgreSQL.

This report does **not** start Research, download datasets, or change strategy logic.

---

## A. Historical universe architecture

Source: public reconstruction [fja05680/sp500](https://github.com/fja05680/sp500), cached at `data/raw/sp500_historical.csv`. **Not** an official S&P Dow Jones Indices feed.

Flow:

```
CSV snapshots (date, tickers)
  → SP500HistoricalSource.parse_snapshots
  → snapshots_to_intervals  [start_date, end_date)
  → validate_memberships
  → PostgreSQL sp500_constituent_memberships
  → UniverseService.snapshot_provider
  → BacktestEngine.get_symbols(as_of) on each monthly signal date
```

Canonical query: `UniverseProvider.get_symbols(as_of)`.

Cached corpus used for this audit: **1259** membership intervals, **1206** unique symbols.

---

## B. PIT membership validation

Intervals are half-open: `start_date <= as_of < end_date`. `end_date is None` means still active.

On the cached file:

| Check | Result |
|-------|--------|
| Duplicate intervals | 0 |
| Overlapping intervals | 0 |
| Impossible date ranges | 0 |
| Fixture `source=test-fixture` in cache | none |
| Current-only leakage into PIT `as_of` | none (re-entrant false positives fixed) |

Ticker strings are uppercased and dataset `-YYYYMM` suffixes are stripped. Share-class marks such as `BRK.B` are not mapped to Yahoo `BRK-B`. There is no Security Master.

---

## C. Rebalance schedule

- First trading session of each month after `lookback_days + 1` warmup sessions **inside** `[start, end]`.
- Strategy evaluates after that session’s close (momentum uses `adjusted_close` with skip/lookback; price/liquidity filters use the signal-date close).
- Target is stored as `pending_target`.
- Orders execute at the **next** session **open**, with configured slippage.

If the last calendar session is itself a rebalance date, the pending target is **not** executed after `end_date`. The engine now records an explicit warning.

---

## D. Look-ahead bias audit

| Channel | Status |
|---------|--------|
| Same-day close used as fill | Blocked. Pending is set after the open-execution block. |
| Future bars in ranking | Blocked by strategy `_slice_as_of` (`timestamp.date() <= as_of`). |
| Future membership | PIT `contains(as_of)` / SQL `start_date <= as_of AND (end_date IS NULL OR as_of < end_date)`. |
| Universe as-of date | Signal date, not execution date. |
| `--universe current` | Survivorship-biased by design; warning emitted. |

Tests: `test_signal_at_t_executes_at_next_open`, `test_fills_never_occur_on_signal_dates`, `test_every_fill_uses_next_open_with_slippage`, `test_look_ahead_future_bars_do_not_change_t_decision`, `test_universe_as_of_is_signal_date_not_execution_date`, `test_future_membership_does_not_change_past_universe`.

---

## E. Universe size by rebalance

Audit walk of calendar month-starts **2015-01-01 → 2025-12-01** on the cached membership file (132 dates):

| | Members |
|--|--|
| Minimum | 499 |
| Maximum | 506 |
| First (2015-01-01) | 499 |
| Last (2025-12-01) | 503 |

The engine uses the **first trading session** of each month, not the first calendar day. Sizes are therefore the PIT membership on that session, typically 500± a few names. Local **price** coverage is a subset of those members (605 local OHLCV files under `data/raw/` at audit time).

---

## F. Suspicious symbols

No ticker blacklist exists in `app/universe`. Previously flagged names were investigated against membership + local prices.

Additional generic extreme-first-close flags (first close ≥ 1000): **CCE**, **HAR**, **PARA**, **TEG**. Bars are **not** dropped; the engine warns when such series are loaded for members in the run window.

---

## G. Ticker changes

Not solved. A rename in the source is a remove of the old ticker and an add of the new ticker when both strings appear. Yahoo often remaps predecessor history onto the current ticker (SQ→XYZ, WWE lineage→TKO). Lookback after eligibility can therefore use remapped predecessor bars. That is a price-identity / corporate-action issue, not a PIT query leak.

---

## H. Delisted handling

Removal sets `end_date` (exclusive). After that date PIT `get_symbols` does not return the name. Missing Yahoo history is reported as missing market data; membership is not deleted. Ticker recycling is not detected at import time.

---

## I. Duplicate / overlapping membership intervals

Cached file: **0 duplicates, 0 overlaps**. Adjacent intervals that share a boundary do not overlap (`[a,b)` + `[b,c)`). Re-entries remain separate intervals and are not merged.

---

## J. Market-data coverage

- Membership ≠ price availability.
- 26 symbols classified as late price start relative to the local corpus (possible recycling or missing delisted history).
- 4 symbols with extreme first close.
- Incomplete local prices mean the strategy sees a **subset** of true PIT members. That is reported, not silently patched.

---

## K. Order count

Authoritative for a run: `len(result.orders)`. Includes FILLED and REJECTED. Risk-failed orders are now recorded as `REJECTED` (previously left `CREATED`). No full 2015–2025 research run was executed for this audit (no large download). Fixture engine runs prove orders are deterministic and every fill maps to exactly one submitted order.

---

## L. Fill count

`result.number_of_trades == len(result.fills)`. One fill per successful order. Partial fills are not implemented. UI label is **Fills** (same integer).

---

## M. Rejected order count

`len([order for order in result.orders if order.status == REJECTED])`. Broker rejects (cash, missing price, short sale) and risk rejects produce **no** fill, **no** cash change, **no** commission, **no** slippage.

---

## N. Commission

`commission = trade_value * commission_rate` with `trade_value = quantity * slipped_fill_price`.

Invariant: `result.total_commission == sum(fill.commission)`.

Default rate: 5 bps (`0.0005`).

---

## O. Slippage

BUY: `slipped = market * (1 + bps/10000)`. SELL: `slipped = market * (1 - bps/10000)`.

Per fill: `slippage = abs(fill_price - market_price) * quantity`.

Invariant: `result.total_slippage == sum(fill.slippage)`.

Default: 10 bps.

---

## P. Accounting reconciliation

Verified in `SimulatedBroker` and engine invariant tests:

| Rule | Status |
|------|--------|
| BUY cash | `-(qty * slipped_price + commission)` |
| SELL cash | `+(qty * slipped_price - commission)` |
| Final cash | initial + sell proceeds − buy costs − commissions |
| Equity | cash + Σ(position_quantity × mark_price) |
| Total return | `final_equity / initial_capital - 1` |
| Fills cannot create cash | rejects unchanged; fills apply the formulas above |
| Short positions | rejected unless held quantity covers the sell |

`Fill.market_price` is the pre-slippage open. `Fill.portfolio_value` is portfolio equity **immediately after the fill** (positions marked at fill prices, not EOD close).

---

## Q. Streamlit consistency

`app/ui/presentation.py` formats `BacktestResult` fields only. It does not recompute return, commission, slippage, or fill count.

| UI | Source |
|----|--------|
| Fills | `result.number_of_trades` |
| Winning / Losing sells | `result.winning_trades` / `result.losing_trades` (SELL vs average cost) |
| Commission | `result.total_commission` |
| Slippage | `result.total_slippage` |
| Total Return | `result.total_return` |
| Fills table | `result.fills` joined to `result.orders` for side |
| Downloads | `app/backtest/export.py` (`fills.csv`, `orders.csv`, `equity_curve.csv`) |

Empty equity no longer short-circuits the fills/download section.

---

## R. Export consistency

Market-data CSV remains OHLCV. Execution export is separate:

| File | Meaning |
|------|---------|
| `fills.csv` | Executions: timestamp, symbol, side, quantity, market_price, fill_price, gross_value, commission, slippage, order_id, portfolio_value, cash, position_quantity |
| `orders.csv` | Order intents including status |
| `equity_curve.csv` | date, equity, cash, returns, drawdown |

CLI `--export-dir` and Streamlit downloads use the same writers. Side is derived from Order. Values are not fabricated.

---

## S. Test results

Executed: `tests/unit` + `tests/backtest` via project venv pytest.

**270 passed, 0 failed.**

Coverage added or extended for PIT boundaries, re-entrant leakage, XYZ/TKO/SE/HAR classification, no blacklist, signal vs execution dates, next-open slippage, trailing pending warning, extreme-price warning (bars kept), rejected orders, cash/equity/commission/slippage invariants, order/fill identity, determinism, execution export, Streamlit fills table and metric labels.

Integration (PostgreSQL) tests were not required for these changes (no `FillModel` migration; backtest results are not DB-persisted).

---

## Investigated symbols

| Symbol | Class | Reason |
|--------|-------|--------|
| XYZ | a — valid historical constituent | Membership `2025-07-23 → open`. SQ never appears in the source. Local prices `2015-11-19 → 2025-12-31` (Yahoo remapped predecessor). PIT eligibility is late and correct. |
| TKO | a — valid historical constituent | Membership `2025-03-24 → open`. Same remapped-predecessor pattern. |
| SE | f — other (ticker recycling) | Spectra Energy `2007-01-03 → 2017-02-27`. Local SE.csv is Sea Limited from `2017-10-20`. **No bars during membership** (safe for selection; contaminates coverage/imports). |
| HAR | f — other (identity mismatch) | Harman `2006-02-01 → 2017-03-13`. Local first close ~18614. Wrong bars **overlap** membership and can be traded. **Warn-only; not blacklisted.** |

---

## Verdict

PASS WITH WARNINGS

---

## Is this backtest trustworthy enough to proceed to Research?

**Yes, with warnings.**

PIT membership algebra, monthly signal-then-next-open execution, and BUY/SELL cash/commission/slippage accounting are consistent and tested. The following remain research caveats, not engine bugs:

1. Unofficial fja05680 membership (not SPDJI).
2. No ticker-change Security Master (XYZ/TKO remapped lookbacks).
3. Ticker recycling / Yahoo identity (SE missing during membership; HAR tradable on wrong prices; also CCE/PARA/TEG extreme first close).
4. Incomplete local price coverage versus true PIT members.
5. `--universe current` is survivorship-biased by design.

No remaining accounting mismatch, PIT look-ahead, or same-day close execution was found.
