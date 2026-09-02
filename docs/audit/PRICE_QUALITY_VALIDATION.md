# Price Quality Validation (PHASE 4)

Data-integrity run only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown from the companion CLI report as research.

Command:

```
python scripts/run_backtest.py --start 2015-01-01 --end 2025-12-31 --universe historical_sp500 --export-dir audit/price_quality_run
```

Artifacts: [audit/price_quality_run/data_quality.txt](../../audit/price_quality_run/data_quality.txt), `fills.csv`, `orders.csv`, `equity_curve.csv`.

## Run summary

| Field | Value |
|-------|--------|
| Period | 2015-01-01 → 2025-12-31 |
| Universe | Historical S&P 500 Point-in-Time (`historical_sp500`) |
| PIT members encountered | 724 |
| PIT universe peak | 506 |
| Market data available | 553 |
| Missing price data | 129 |
| Unusable price series | 3 (CCE, HAR, PARA) |
| Insufficient history | 39 |
| Fills involving unusable symbols | none |
| Orders | 1509 |
| Fills | 1509 |
| Rejected orders | 0 |
| Stuck unvalued positions | ESRX |
| Stale last-price MTM after series end | no |
| Final status | DATA_QUALITY_INCOMPLETE |
| Research readiness | NOT READY |

## Investigated symbols

Classification uses only this run’s membership, local bars, fills, and quality diagnostics. No ticker blacklist.

| Symbol | What the data shows |
|--------|---------------------|
| HAR | PIT member in-window. Local first close ~18614. Quality = unusable (`extreme_first_close`). **0 fills, 0 orders.** Membership not dropped. |
| PARA | PIT member in-window. Local first close ~101500. Quality = unusable. **0 fills, 0 orders.** Membership not dropped. |
| CCE | PIT member in-window. Local first close ~1112. Quality = unusable. **0 fills, 0 orders.** Membership not dropped. |
| TEG | Membership `2007-02-22 → 2015-06-30`. First rebalance in this engine is after 253 in-window warmup sessions (~2016), so TEG was never a rebalance member here. Local TEG bars start `2015-12-22` (after membership ended) with first close ~8207. **0 fills, 0 orders.** Same generic extreme-first-close rule would mark those bars unusable if they were candidates. |
| SE | Spectra Energy membership ends `2017-02-27`. Local `SE.csv` starts `2017-10-20` (Sea Limited, first close ~16.26). No bars during membership. **0 fills.** Not treated as a valid member because later Sea Limited prices exist. |
| GME | Local first close ~10.66 (usable). **0 fills** in this run. At least one rebalance skipped GME for `min_price`. Not identity-failed. |
| XYZ | Local first close ~13.07 (usable). **0 fills** in this run. PIT eligibility remains a late 2025 add. Security Master treats SQ→XYZ as the same Class A with Yahoo continuity; see [SECURITY_MASTER_AUDIT.md](SECURITY_MASTER_AUDIT.md). |
| TKO | Local first close ~10.67 (usable under the price-quality heuristic). Security Master clips Yahoo bars before 2023-09-12 (WWE predecessor). Not blacklisted. |

CVNA / APP / HOOD were not classified.

## Ended-series MTM

ESRX was bought `2018-12-04` (86 shares). Local series ends `2018-12-21`. On `2018-12-24` the engine left the position **unvalued** (not marked at last price). Later sessions warn `missing open for execution` and do not fill a sell. `Stale last-price MTM after series end: no`.

NAV after that date excludes ESRX. That is incomplete accounting by design, not a silent last-price hold.

## Remaining blockers (PHASE 5 still blocked)

1. Incomplete local prices versus PIT members (129 missing in this window).
2. Security Master exists for seeded known cases only; see [SECURITY_MASTER_AUDIT.md](SECURITY_MASTER_AUDIT.md). Unmapped PIT names remain identity-unproven. PARA/CCE/TEG identities are unresolved.
3. Unofficial fja05680 membership source.
4. Extreme-first-close threshold is a generic heuristic, not a complete corporate-action identity model.
5. Unvalued residuals (ESRX here) make the equity curve incomplete for research.
6. `--universe current` remains survivorship-biased if used.

**research_ready = false**
