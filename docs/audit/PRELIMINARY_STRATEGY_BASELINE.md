# Preliminary Strategy Baseline

**STATUS: PRELIMINARY / NOT RESEARCH-GRADE**

**RESEARCH_READY: NO**

This is an exploratory single-run baseline of the existing 12-1 momentum
implementation on the current dataset. It is **not** strategy validation.
Parameters were not changed. The strategy was not modified. Phase 5 was not
started.

Companion exports (existing backtest export format; not a new storage system):

- [`audit/preliminary_strategy_baseline/equity_curve.csv`](../../audit/preliminary_strategy_baseline/equity_curve.csv)
- [`audit/preliminary_strategy_baseline/fills.csv`](../../audit/preliminary_strategy_baseline/fills.csv)
- [`audit/preliminary_strategy_baseline/orders.csv`](../../audit/preliminary_strategy_baseline/orders.csv)
- [`audit/preliminary_strategy_baseline/data_quality.txt`](../../audit/preliminary_strategy_baseline/data_quality.txt)
- [`audit/preliminary_strategy_baseline/cli_stdout.txt`](../../audit/preliminary_strategy_baseline/cli_stdout.txt)
- [`audit/preliminary_strategy_baseline/cli_stderr.txt`](../../audit/preliminary_strategy_baseline/cli_stderr.txt)

Run date: **2026-09-03**.

Exact command (frozen; no parameter overrides):

```bash
source .venv/bin/activate
python scripts/run_backtest.py \
  --start 2015-01-01 \
  --end 2025-12-31 \
  --capital 100000 \
  --universe historical_sp500 \
  --verbose \
  --export-dir audit/preliminary_strategy_baseline
```

No production code was changed. The run used the existing tested implementation
(`tests/backtest/`). The relevant test suite was not re-run because there was
no correctness fix.

---

## 1. Experiment objective

Answer only:

> Is there enough signal in the current baseline implementation to justify
> investing further effort in research-grade data and systematic strategy
> research?

Do not treat the numbers below as a research result.

---

## 2. Exact strategy parameters

Effective values from `Settings` / `MomentumConfig` / `BacktestConfig` (defaults;
`.env` does not override them). **Not changed for this run.**

| Parameter | Value |
|-----------|--------|
| Lookback | 252 trading days |
| Skip / recent exclusion | 21 trading days |
| Top N | 10 |
| Minimum price | $10 |
| Dollar-volume window | 20 trading days |
| Minimum dollar volume | $20,000,000 |
| Weighting | equal weight (`PortfolioService`: `1 / N` among eligible) |
| Rebalance | monthly (first session of each month after warmup) |
| Signal timing | after market close on the rebalance date |
| Execution | next trading session open |
| Slippage | 10 bps (`settings.slippage = 0.001`) |
| Commission | 5 bps (`BacktestConfig.commission_rate = 0.0005`) |
| Initial capital | $100,000 |
| Warmup sessions | 253 (`lookback_days + 1`) |
| History load buffer | `lookback_days * 2 + 40` calendar days before start (~2013-07-06) |

Skip=21 is the recent endpoint **inside** the 252-day window
(`adj_close[t-21] / adj_close[t-252] - 1`). It is not extra warmup of 273
sessions.

---

## 3. Universe mode

**Actually used: `historical_sp500`** (Historical S&P 500 Point-in-Time).

Not used: `current` S&P 500, explicit `--symbol` lists, or “all CSV files.”

Membership comes from PostgreSQL PIT constituents (`sp500_constituent_memberships`,
1259 intervals; 754 names overlapping 2015-01-01 → 2025-12-31). Market data
comes from PostgreSQL `market_bars` via `OfflineMarketDataProvider`. The engine
applies PIT membership per rebalance date.

The run itself warns: this is **not** a full S&P 500 historical backtest
because local prices are incomplete.

---

## 4. Date range

| Item | Value |
|------|--------|
| Requested start | 2015-01-01 |
| Requested end | 2025-12-31 |
| First equity point (calendar) | 2015-01-02 |
| First rebalance | **2016-01-04** (253rd in-window session; 252 sessions in 2015) |
| First fill | **2016-01-05** 09:30 (next session open) |
| Last rebalance | **2025-12-01** |
| Last fill | 2025-12-02 09:30 |
| Last equity point | 2025-12-31 |
| Equity sessions | 2766 |
| Rebalances | 120 |

The period was not shortened after seeing results.

---

## 5. Data source/state

| Item | Value |
|------|--------|
| `DATA_PROVIDER` | CSV (backtest reads PostgreSQL via `OfflineMarketDataProvider`) |
| CSV cache | `data/raw` (not overwritten) |
| PostgreSQL | localhost:5433 `momentum_trader` |
| Security Master | `data/security_master/known_identities.json` (seeded exceptions only) |
| PIT members encountered | 724 |
| PIT universe peak | 506 |
| PIT members per rebalance | 503–506 |
| Market data available (coverage snapshot) | 564 |
| Missing market data | 115 |
| Unusable series | 3: CCE, HAR, PARA |
| Insufficient history (unique, run-level) | 42 |

No CSVs were overwritten. No `market_bars` writes. No PIT membership edits.
No blacklist.

---

## 6. Execution assumptions

Existing engine semantics, unchanged:

1. Signal after close on the rebalance date.
2. Target portfolio equal-weight top 10 (or fewer if fewer eligible).
3. Orders execute at the next session’s open.
4. Slippage 10 bps on the open.
5. Commission 5 bps on fill value.
6. EOD mark-to-market at close.
7. Missing execution open → no fill + warning.
8. Ended series → unvalued residual; no invented sale.
9. No silent forced liquidation.

This run: **0** “missing open for execution” warnings; **0** stuck unvalued
positions; **0** rejected orders; **0** fills in unusable symbols.

---

## 7. Performance results

**PRELIMINARY / NOT RESEARCH-GRADE.** Incomplete PIT prices. Unofficial
membership. Identity unresolved for most names.

| Metric | Value |
|--------|--------|
| Initial capital | $100,000.00 |
| Final NAV | $193,743.27 |
| Total return | 93.74% |
| CAGR | 6.20% |
| Annualized volatility | 28.23% |
| Sharpe (rf = 0) | 0.36 |
| Maximum drawdown | −45.90% (trough 2020-03-20) |
| Max drawdown duration | **Not an engine metric.** From `equity_curve.csv`: peak 2018-08-29 → trough 2020-03-20 → recovered 2021-02-12 (618 sessions). |
| SPY buy-and-hold | **Unavailable.** Engine computes it only if `SPY` bars appear in the session calendar. SPY is not a PIT S&P 500 constituent, so it was not loaded. No improvised benchmark. |

Equity-curve inspection (existing CSV; not a new visualizer):

- All-cash $100,000 from 2015-01-02 until first fills on 2016-01-05 (warmup).
- Peak equity $201,745.31 on 2025-12-10.
- Trough $62,387.67 on 2020-03-20.
- Largest daily moves cluster in March 2020 and April 2025 (order of 9–15%).
  That is crisis-like volatility, not an obvious one-day NAV discontinuity
  from a bad fill.
- End-2025 NAV is below the 2025-12-10 peak.

---

## 8. Trading statistics

| Metric | Value |
|--------|--------|
| Rebalances | 120 |
| Orders | 1522 |
| Fills | 1522 (`number_of_trades` = fill count; no Trade type) |
| Rejected orders | 0 |
| Fill sides | 761 BUY, 761 SELL |
| Unique symbols filled | 226 |
| Unique fill dates | 120 (one execution session after each rebalance) |
| Turnover | **Not instrumented** by the engine. Fills/rebalance ≈ 12.7. |
| Average number of holdings | **Not instrumented.** Every rebalance selected **10**. |
| Average portfolio exposure | ~90.3% (1 − cash/equity), including 2015 all-cash warmup; ~99.4% after first invest date |
| Average cash percentage | ~9.7% including warmup; ~0.6% after first invest date |
| Total commission | $5,009.56 |
| Total slippage | $10,019.03 |

Per-rebalance **selected symbols and weights** are **not stored** in
`RebalanceDiagnostics` (counts only). They were not reconstructed into a new
analytics system. Target weights are equal `1/10` when 10 names are selected.

---

## 9. Data-quality diagnostics

Engine `DATA_QUALITY_VALIDATION` status: **DATA_QUALITY_INCOMPLETE**.

| Diagnostic | Count |
|------------|--------|
| PIT securities considered (unique) | 724 |
| PIT peak | 506 |
| Excluded for missing local prices | 115 (peak 93 missing on a rebalance; 120 dates affected) |
| Excluded for unusable price / identity | 3 (CCE, HAR, PARA). HAR = identity_mismatch (Harman vs recycled local series); CCE/PARA = extreme_first_close. **0 fills.** Membership kept. |
| Insufficient history | 42 unique (run-level set) |
| Unvalued residual positions | none in this run |
| Result.warnings | missing-data summary; unusable-series summary; “NOT a full S&P 500 historical backtest” |
| Filter skip logs (stderr) | 19,798 lines — per-name skip reasons (`non-positive momentum`, `min_price`, `insufficient history`, liquidity). Expected filter behavior, not invented prices. |

Rebalances with unusually low **momentum-eligible** counts (still selected 10):

| Date | Eligible | Universe members |
|------|----------|------------------|
| 2020-05-01 | 80 | 505 |
| 2022-11-01 | 117 | 503 |
| 2016-03-01 | 124 | 505 |
| 2019-02-01 | 137 | 505 |

Missing-price sample from the engine warning includes ATVI, AVB, BK, CBS, CA,
ADS, and other names already documented in Phase 4 coverage work. No aliases
were invented.

---

## 10. Sanity-check results

| Check | Result |
|-------|--------|
| 1. First rebalance after 252+21 history | **PASS.** In-window warmup is 253 sessions. 252 sessions elapse in 2015; first month-start after that is 2016-01-04 (the 253rd session). Skip=21 is inside the 252-day window. Pre-start bars are loaded from ~2013-07 for the lookback. |
| 2. Look-ahead | **PASS (existing design).** Signal uses history through the rebalance close. Orders are deferred (`pending_target`) and filled on the **next** session open. No fill date equals a rebalance date. |
| 3. Execution next session | **PASS.** Rebalance 2016-01-04 → first fills 2016-01-05 09:30. Last rebalance 2025-12-01 → fills 2025-12-02 09:30. 120 rebalances, 120 fill dates. |
| 4. Costs reflected | **PASS.** First AMZN fill: market 32.342999, fill 32.375342 (exactly 10 bps), commission 4.9858 on ~9971.61 (exactly 5 bps). All 1522 fills have non-zero commission and slippage. Totals $5,009.56 commission and $10,019.03 slippage. |
| 5. Ended-series valuation | **PASS for this run.** No stuck unvalued positions; no “holding last price” warnings. (Ended-series residuals remain possible in other paths; accounting was not changed.) |
| 6. PIT universe | **PASS.** Report label: Historical S&P 500 Point-in-Time. 503–506 members per rebalance, not “today’s S&P” (503 current-active) and not CSV-stem dump. |
| 7. Missing data | **PASS.** Missing names are skipped with warnings; not zero-priced. Unusable CCE/HAR/PARA cannot fill. Stderr skip reasons are filters, not invented returns. |
| 8. Effective parameters | **PASS.** Printed in §2; match `MomentumConfig` / `BacktestConfig` defaults. `.env` has no strategy overrides. |

No correctness bug was found. No strategy code was changed.

---

## 11. Important limitations

1. 115 PIT names have no local prices (delisted / identity / download holes).
   Survivorship in the *available* subset can bias momentum **upward**.
2. Security Master remains a seeded-exceptions catalog. Most window names stay
   identity-UNRESOLVED. Yahoo ticker-row path is still used for most names.
3. Official S&P membership is still unofficial (fja05680).
4. HAR / PARA / CCE remain unusable; membership was not dropped.
5. Sharpe uses rf = 0. Max DD duration is not a first-class metric.
6. No benchmark in this run (SPY not in PIT load).
7. Selected tickers per rebalance are not persisted.
8. This is one frozen parameter set. It is not an optimum.

---

## 12. Interpretation

Exploratory classification: **INCONCLUSIVE**

The implementation produces a functioning long-only 10-name monthly book:
positive total return (93.74%, CAGR 6.20%), costs applied, PIT membership
applied, no fill of known identity-mismatch names. That is **not** a
demonstration that “the strategy works.”

Risk-adjusted numbers are weak (Sharpe 0.36, volatility 28%, drawdown −46%).
The dataset is missing 115 rebalance-visible names, which is exactly the
failure mode that can manufacture a survivorship-biased momentum result.

Therefore the result is too **data-limited** and too **modest on a risk-adjusted
basis** to call the signal PROMISING, and it is not a realized loss that would
make the baseline NEGATIVE.

This classification is exploratory only. **INCONCLUSIVE does not mean Research
Ready.** A PROMISING label would also not mean Research Ready.

---

## 13. Next-step recommendation

Continue **Phase 4 — Historical Data Quality** (Norgate trial protocol; do not
mass-download; do not integrate a provider yet).

Do **not**:

- start Phase 5 Strategy Research
- sweep lookback / skip / Top N / filters / costs
- start robustness tests or paper trading
- treat this CAGR/Sharpe as a research finding

Hypothesis for a **future** experiment (not tested now): filling delisted and
identity-safe names may *lower* this baseline if the current 6.2% CAGR is
partly survivorship in the local CSV subset.

---

PHASE 4 — Historical Data Quality: **IN PROGRESS**

PHASE 5 — Strategy Research: **NOT STARTED**

**RESEARCH READY: NO**
