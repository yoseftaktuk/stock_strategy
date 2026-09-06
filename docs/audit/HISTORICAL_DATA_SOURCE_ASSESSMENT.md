# Historical Data Source Assessment (Round 11)

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

**Assessment only.** No new vendor was wired into production. PostgreSQL
`market_bars`, PIT schema, Yahoo CSVs, broker accounting, and Strategy
Research were not modified.

Assessment date: **2026-09-06**.

Prior evidence (not erased):

- [HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md](HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md)
- [NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md)
- [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md)
- [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md)
- [SECURITY_MASTER_AUDIT.md](SECURITY_MASTER_AUDIT.md)
- [PRICE_QUALITY_VALIDATION.md](PRICE_QUALITY_VALIDATION.md)
- Round 10 domain contracts: `app/domain/price_semantics.py`,
  `app/domain/corporate_actions.py`

Machine-readable matrix:

- [`audit/historical_data_assessment/capability_matrix.json`](../../audit/historical_data_assessment/capability_matrix.json)

---

## Gates (do not collapse)

| Gate | Meaning | Status |
|------|---------|--------|
| Vendor validation | Can the vendor correctly represent the tested 2-year cases? | **true** (Trial window 2024-09-03 → 2025-12-31). Not re-run here. |
| Construction readiness | Can we construct the required research dataset? | **true** (GO to continue infrastructure). Not permission to ingest production. |
| Research readiness | Can we run scientifically valid Strategy Research? | **false** |

`full_historical_research_ready` remains **false**. Phase 5 remains
**NOT STARTED**.

---

## 1. Required research dataset contract

The research dataset must support accounting, identity, and universe
contracts already frozen in this repo. Events are never inferred from
adjusted prices (`infer_actions_from_prices` returns empty).

### 1.1 Price history

| Requirement | Why |
|-------------|-----|
| Daily OHLC | Execution (next-session **open**), mark (**close**), range checks |
| Volume | Dollar-volume liquidity filter (`close * volume` on the current path) |
| Documented raw **or** documented split-adjusted OHLC | Round 10: Yahoo Close is split-adjusted, not raw. Accounting cannot treat it as unadjusted. |
| Total-return / dividend-adjusted series | Momentum uses **`adjusted_close` only** (`lookback_days=252`, `skip_days=21`) |
| Historical depth | Evaluation **2015-01-01 → 2025-12-31** plus warmup typically **2013-07-08** (253 sessions) |

Price roles (`PriceSemantics`) are not interchangeable:

- EXECUTION = next-session open
- MARK = close
- SIGNAL = adjusted_close
- TERMINAL = close, no slippage

### 1.2 Corporate actions

Required inputs for the domain contract (`CorporateAction`):

| Event | Required input | Accounting effect |
|-------|----------------|-------------------|
| Split / reverse split | `factor > 0` | qty × factor; price ÷ factor; average_price ÷ factor; cash unchanged |
| Cash dividend | `amount` per share | cash += qty × amount; qty unchanged; tape not rewritten |
| Merger / acquisition | explicit cash-per-share and/or share conversion terms | missing terms → **UNRESOLVED** |
| Delisting | known terminal proceeds if available | else last quoted close is only a **proxy**, not proceeds |

The current Yahoo tape implements `EmptyCorporateActionProvider`.

### 1.3 Identity

Canonical identity is internal `security_id` / `seed_key`. Ticker is never
canonical.

Invariants that any vendor mapping must preserve:

| Case | Required outcome |
|------|------------------|
| SQ → XYZ | same security, same `position_key` |
| SE Spectra → Sea | different securities, different `position_key` |
| ESRX → CI | different securities; do not alias to acquirer |
| BRK.B / BF.B | distinct share classes (and distinct from Class A) |
| Ticker recycle | distinct listings / occupancies |

### 1.4 PIT universe

Must reconstruct membership **as it was known on date D**, not today's list.

| Requirement | Current project source |
|-------------|------------------------|
| Historical constituents | unofficial fja05680 cache `data/raw/sp500_historical.csv` |
| Effective dates | half-open `[start, end)` intervals |
| Point-in-time membership | `UniverseProvider.get_symbols(as_of)` |
| Survivorship-bias-free construction | `historical_sp500` yes for membership; `--universe current` is survivorship-biased |

fja05680 remains **unofficial**. It must not be silently promoted.

### 1.5 Data quality

Corrections/revisions behavior, missing bars, stale prices, delisted
securities, and corporate-action consistency with identity must be
observable. A missing name stays in the universe; it is not dropped
because prices are absent.

---

## 2. Current Yahoo capability assessment

**Do not modify.** Path: `yfinance` `auto_adjust=False` → CSV
`data/raw/{SYMBOL}.csv` → PostgreSQL `market_bars`.

Schema: `open, high, low, close, adjusted_close, volume`.

Round 10 semantics (AAPL 4-for-1 2020-08-31 fixture):

- `open/high/low/close` = **split-adjusted**, not dividend-adjusted, **not raw**
- `adjusted_close` = **split + dividend** adjusted
- no event columns

### What Yahoo can provide

| Topic | Assessment | Evidence |
|-------|------------|----------|
| Historical depth | **PARTIAL** | Local listed files (e.g. AAPL/MSFT) cover **2013-07-08 → 2025-12-31** (3142 sessions). Yahoo can go earlier for many live names. Warmup corpus is this window, not 1950s. |
| Symbol coverage | **PARTIAL** | 607 local ticker CSVs (excluding `sp500_historical.csv`). Coverage audit: 754 PIT names overlapping 2015–2025; 604 valid; 150 missing; 8 partial; 2 unusable. |
| Delisted coverage | **UNSUPPORTED** as primary | 68 acquired/delisted of the 113 have no safe Yahoo series. Recycle fetches return the wrong issuer (`SE.csv` is Sea from 2017-10-20, not Spectra). |
| Corporate-action availability | **UNSUPPORTED** on the stored tape | No split/dividend/merger table. yfinance `actions` is unused and must not be inferred into events. |
| Identity quality | **UNSUPPORTED** | Ticker-keyed. Remaps history onto the current symbol (SQ history served as XYZ). Recycles (`SE`, `HAR`). No stable ID. |
| PIT suitability | **UNSUPPORTED** | Yahoo is not a constituent feed. |
| Survivorship | **UNSUPPORTED** | Using live Yahoo as the universe is current-listed bias. Even with PIT membership, missing delisted prices bias momentum **upward**. |
| Secondary / validation | **SUPPORTED** for currently listed, identity-safe names | Useful cross-check of Norgate TOTALRETURN vs Yahoo Adj Close **after** Security Master mapping. Never primary for recycle/delisted. |

`YAHOO_CURRENT_TAPE` already records: no raw OHLC, no split/dividend events,
no merger terms, no delisting proceeds; last quoted close is only a known
delisting **proxy**.

---

## 3. Norgate Trial capability assessment

Not a re-validation of the 2-year GO. Trial window remains
**2024-09-03 → 2025-12-31**.

Live Trial evidence already in-repo
([`audit/norgate_trial/vendor_coverage_probe.json`](../../audit/norgate_trial/vendor_coverage_probe.json)):

- Windows 11 ARM64, NDU running, `norgatedata` importable
- Databases included `US Equities` **and** `US Equities Delisted`
- Listed controls resolved with `first_quoted_date=2024-09-03` (GME
  assetid `124739`, XYZ `2104402`, Sea/SE `2326776`, TKO `144819`,
  GEN `146955`, RVTY `130027`)
- Pre-window delisted suffixes (`ATVI-202310`, `SE-201702`, `HAR-201703`,
  `ESRX-201812`, …) were **NOT_FOUND** — Trial depth, not a Platinum miss
- SQ current ticker NOT_FOUND; history lives on **XYZ** (documented
  prepend-to-current-symbol behavior)
- This Mac: `norgatedata` **not installed**; NDU **not present** (2026-09-06)

Official Trial SKU (not assumed equal to paid Platinum depth): 2 years of
history, daily updates during the trial, **includes** delisted securities
and historical index constituents **at Trial depth**.

| Question | Trial | Evidence class |
|----------|-------|----------------|
| 1. Historical unadjusted OHLC | **PARTIAL** | Documented `StockPriceAdjustmentType.NONE` + Unadjusted Close column. Live Trial queried TOTALRETURN and NONE with a 3-bar limit; not a full unadjusted tape proof. |
| 2. Split events | **UNKNOWN** as an event table | Not probed. Documented: no direct split-detail feed (see §4). |
| 3. Dividend events | **PARTIAL / UNKNOWN** | Documented Dividend column when adjustment is not TOTALRETURN. Not live-proven on Trial. |
| 4. Merger/acquisition information | **UNSUPPORTED** for terms | FAQ: surviving-entity / merger-of-equals **identity** rules only. No cash/share conversion terms. |
| 5. Delisting prices | **PARTIAL** | `last_quoted_date` + last bars when the name is in the 2-year tape. Pre-window delists NOT_FOUND. FAQ: no delisting return. |
| 6. Historical S&P 500 constituents | **UNKNOWN** live | Trial SKU claims historical constituents; `$SPX` cross-check was optional and **not** executed as a live membership dump in the frozen 37-row probe. |
| 7. PIT constituent membership | **UNKNOWN** live | `index_constituent_timeseries` is documented; not live-proven on Trial artifacts. |
| 8. Stable vendor identity | **PARTIAL** | Live `assetid` for in-window listed names. Pre-window occupancies untestable on Trial. |
| 9. Ticker history | **UNSUPPORTED** | Official FAQ: prior symbols are **not** provided. |
| 10. Share-class identity | **UNKNOWN** | Sea name included “Class A ADR”. BRK.B vs BRK.A not live-tested. |
| 11. Historical depth required by the project | **UNSUPPORTED** | 2-year tape cannot cover 2013-07-08 → 2025-12-31. |
| 12. Access from current Mac | **UNSUPPORTED** | NDU is Windows-only. No VM/NDU/`norgatedata` here. |
| 13. Export/API limitations | **PARTIAL** | Local Python API, no REST, no rate limit (local DB). Must not dump `database_symbols()`. ASCII export is prices/volume only. |
| 14. Licensing | **PARTIAL** | Personal use, two machines, Trial then paid sub. Content must be deleted when the subscription/trial ends; **Derived Data** (backtest results) may be retained. No commercial license. |

Trial cannot be used as the Strategy Research tape.

---

## 4. Norgate full-data (US Stocks Platinum) capability assessment

Do **not** treat Trial behavior as the paid dataset. Platinum is the
documented **full-history class** (history to **1990**, delisted, OTC
formerly listed, historical index constituents). Diamond extends listed
and delisted history to **1950**. Silver/Gold **exclude** delisted and
historical constituents — insufficient.

Sources checked 2026-09-06 (documentation, not a live Platinum query):

- https://norgatedata.com/stockmarketpackages.php
- https://norgatedata.com/data-content-tables.php
- https://norgatedata.com/data-package-faq.php
- https://pypi.org/project/norgatedata/
- https://norgatedata.com/subscribe/eula.php
- https://norgatedata.com/faq.php

| Question | Full Platinum | Evidence class |
|----------|---------------|----------------|
| 1. Historical unadjusted OHLC | **SUPPORTED** (documented) | `NONE` adjustment; Unadjusted Close in `price_timeseries`; `unadjusted_close_timeseries`. **Not live-proven** on this Mac. |
| 2. Split events | **PARTIAL** | `capital_event_timeseries` is a **boolean** (1/0) for splits, reverse splits, bonus issues, complex reorganizations. FAQ: “Do you provide details on corporate action events such as splits and dividends? **No, not directly.**” No split **factor** event table in the Python API. Cannot feed `qty × factor` without inferring from prices (forbidden) or another source. |
| 3. Dividend events | **PARTIAL** | Dividend **amount** column on `price_timeseries` when adjustment is CAPITAL / CAPITALSPECIAL (entitlement = day **before** ex-date). TOTALRETURN hides the column. `dividend_yield_timeseries` is trailing-12m yield, not an event. Not a standalone dated event table with payment vs ex-date. |
| 4. Merger/acquisition information | **PARTIAL** identity / **UNSUPPORTED** terms | Surviving entity keeps `assetid`; non-survivor delisted; merger-of-equals → new `assetid`. **No cash consideration, no share-conversion ratio.** FAQ: “there is no single value that could be supplied consistently for every event.” |
| 5. Delisting prices | **PARTIAL** | Last traded bar + `-YYYYMM` suffix + `last_quoted_date`. FAQ: **no delisting return**, no delist reason. Users typically flatten on the final bar. Matches this repo’s last-close **proxy**, not true proceeds. |
| 6. Historical S&P 500 constituents | **SUPPORTED** (documented) | `$SPX` constituents from **Mar 1957**, Platinum/Diamond. **Not** an official S&P Dow Jones licensed feed for this project. Temporary inclusions are **not** included. No announcement dates. |
| 7. PIT constituent membership | **SUPPORTED** (documented) | `index_constituent_timeseries(symbol, 'S&P 500' or '$SPX')` true/false as-of. Watchlists are **not** PIT. |
| 8. Stable security/vendor identity | **SUPPORTED** (documented) | Integer `assetid` survives ticker change, exchange move, delisting. Store as `NORGATE_ASSETID` attribute — never replace `security_id`. |
| 9. Ticker history | **UNSUPPORTED** | “No, only the current symbol is provided.” History is prepended onto the current symbol. Occupancy mapping remains **this** project’s Security Master (PIT ticker + as-of → current or `TICKER-YYYYMM`). |
| 10. Share-class identity | **UNKNOWN** | Distinct listings should have distinct `assetid`s; BRK.B vs BRK.A not live-proven. CIK is not provided as a Norgate field. |
| 11. Historical depth | **SUPPORTED** for this project’s window | Platinum to 1990 covers 2013-07-08 → 2025-12-31. Completeness of every S&P dropout is **UNKNOWN** until a Platinum sample (the 113). Nasdaq pre-1982 is documented weaker; irrelevant to 2015–2025. |
| 12. Access from current Mac | **UNSUPPORTED** natively | NDU Windows-only. Python must run **inside** the Windows environment. First-time US Platinum: ~2 GB download / ~9.1 GB on disk (prior protocol). |
| 13. Export/API | **PARTIAL** | Local `norgatedata`, no rate limits, no generic remote API. Query by symbol **or** `assetid`. Corrections applied continuously **without notification**. Database inaccessible after subscription expiry. |
| 14. Licensing | **PARTIAL / constraint** | Personal use only (individual trading/research/academic). **No commercial license.** Two personal machines. No redistribution. On expiry: delete Content; retain Derived Data (backtest statistics/rules). S&P index data reproduction restricted by SPDJI clause in the EULA. |

**Cannot claim** Platinum currently contains ATVI, Spectra-SE, HAR/Harman, or
every name in the 113. That remains a **future Platinum coverage proof**.
Documented capability class is delisted-aware; live proof is still the
2-year Trial only.

---

## 5. Alternative architecture assessment

No option is implemented.

### Option A — Unadjusted OHLC + separate corporate-action feed

**Advantages.** Execution/mark/terminal can use economic prints. Splits
apply as `qty × factor` on a tape that still shows the pre-split print.
Audit: events are explicit rows.

**Disadvantages.** Requires a **true** event table with factors and cash
amounts. Yahoo cannot supply this. Norgate supplies unadjusted close but
**not** split factors as events. Sharadar ACTIONS (documented) is closer.

**Accounting.** Matches the Round 10 contract if events are complete.
Mergers still UNRESOLVED without terms.

**Identity.** Independent. Events must key on `security_id` / `listing_id`,
not ticker.

**PIT.** Independent.

**Complexity.** High: new CA store, engine wiring, split vs dividend
ordering, fractional shares.

**Auditability.** Highest if events are dated and sourced.

### Option B — Split-adjusted OHLC + separate corporate-action feed

**Advantages.** Matches current Yahoo Close semantics and Norgate CAPITAL
OHLC. Momentum can keep Adj Close / TOTALRETURN. Avoids rewriting the
entire listed tape.

**Disadvantages.** Applying split events **again** on split-adjusted OHLC
double-counts. Dividend cash events must not also rewrite Close. Easy to
get wrong.

**Accounting.** Splits should **not** rescale a already-split-adjusted
mark. Dividends can still credit cash if the mark is not dividend-adjusted.
Yahoo Close is not dividend-adjusted — cash dividends are still missing
from the ledger today.

**Identity / PIT.** Independent.

**Complexity.** Medium-high: must document “do not apply split to this
tape.”

**Auditability.** Medium: two adjustment layers.

### Option C — Vendor total-return series + separate accounting events

**Advantages.** Signals stay on TOTALRETURN / Adj Close. Accounting ledger
uses explicit cash/stock events. Clean role split (already in
`PriceSemantics`).

**Disadvantages.** Still needs an event feed for cash and mergers.
TOTALRETURN already embeds dividends — crediting cash **and** using TR
marks overstates economic P&L if mixed carelessly. Terminal/mark must
remain **unadjusted or split-adjusted Close**, never TR.

**Accounting.** Viable if roles stay strict.

**Complexity.** Medium if the vendor already has TR + unadjusted close
(Norgate does, documented).

**Auditability.** Good if roles are logged.

### Option D — Vendor-native backtest / security master dataset

**Advantages.** Norgate+Zipline or Sharadar+QuantRocket already combine
prices, PIT, and adjustments.

**Disadvantages.** Domain would depend on vendor APIs — **forbidden** by
provider independence. Surviving-entity rules may disagree with TKO / ESRX
/ LLL. fja05680 would be replaced silently. Not auditable inside this
engine.

**Complexity.** Appears low; integration cost and identity risk are high.

**Auditability.** Lowest for this repo.

**Recommendation among A–D (design only):** **C as the signal/mark split,
with A-style events if a real event table is acquired.** Do not pick D.
Do not apply Option A splits onto the current Yahoo tape.

---

## 6. Capability matrix

Every cell is SUPPORTED / PARTIAL / UNSUPPORTED / UNKNOWN.

**Alternative** = Sharadar SEP **as documented** (Nasdaq Data Link / QuantRocket
public pages, 2026-09-06). **Not live-queried** (no credentials). CRSP is
the research-grade upgrade and is **not licensed** here.

| Capability | Yahoo current | Norgate Trial | Norgate full (Platinum, documented) | Alternative (Sharadar SEP, documented) |
|------------|---------------|---------------|--------------------------------------|----------------------------------------|
| Historical OHLC | SUPPORTED (split-adjusted listed names) | PARTIAL (from 2024-09-03; listed names that resolved) | SUPPORTED (to 1990) | SUPPORTED (from 1998, active+delisted) |
| Raw OHLC | UNSUPPORTED | PARTIAL (NONE API documented; not fully live-proven) | SUPPORTED (documented Unadjusted Close / NONE) | SUPPORTED (documented `closeunadj`) |
| Adjusted OHLC | PARTIAL (Adj Close only; OHLC not dividend-adjusted) | PARTIAL (TOTALRETURN Close documented; 2-year) | SUPPORTED (TOTALRETURN / CAPITAL modes) | SUPPORTED (split-adj OHLC + `closeadj` TR) |
| Split events | UNSUPPORTED | UNKNOWN | PARTIAL (boolean capital event; **no factor table**) | SUPPORTED (ACTIONS `split`; terms completeness UNKNOWN) |
| Dividend events | UNSUPPORTED | PARTIAL/UNKNOWN (Dividend column documented, not live-proven) | PARTIAL (amount on timeseries if not TOTALRETURN; no full event table) | SUPPORTED (ACTIONS cash/stock dividends) |
| Merger terms | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED (identity rules only; no cash/share terms) | PARTIAL (ACTIONS includes acquisitions; cash/share terms UNKNOWN) |
| Delisting proceeds | UNSUPPORTED (last-close proxy only) | PARTIAL (in-window last bar; pre-window NOT_FOUND) | PARTIAL (last bar; **explicitly no delisting return**) | PARTIAL (delist **reasons** documented; proceeds UNKNOWN) |
| Security identity | UNSUPPORTED (ticker) | PARTIAL (live `assetid` for in-window listed) | SUPPORTED (documented `assetid`) | SUPPORTED (documented `permaticker`) |
| Ticker history | UNSUPPORTED (remap / recycle) | UNSUPPORTED (FAQ: no prior symbols) | UNSUPPORTED (same FAQ) | SUPPORTED (ACTIONS ticker changes; not live-proven) |
| Historical constituents | UNSUPPORTED | UNKNOWN live (SKU claims it at 2-year depth) | SUPPORTED (`$SPX` from 1957; **unofficial vs SPDJI**) | SUPPORTED (vendor S&P adds/removes since 1957; **unofficial vs SPDJI**) |
| PIT membership | UNSUPPORTED | UNKNOWN live | SUPPORTED (`index_constituent_timeseries`) | PARTIAL (constituent history tables; as-of API not live-proven here) |
| Survivorship-free | UNSUPPORTED | UNSUPPORTED (2-year listed-heavy tape) | PARTIAL (designed for it at Platinum; completeness of the 113 UNKNOWN; membership not official) | PARTIAL (delisted+constituents documented; completeness UNKNOWN) |
| Historical depth | PARTIAL (listed 2013–2025 local; delisted holes) | UNSUPPORTED vs 2013–2025 | SUPPORTED vs 2013–2025 (Platinum to 1990) | SUPPORTED vs 2013–2025 (prices from 1998) |

---

## 7. Research-window recommendation

Configured windows **already in this project** (not invented):

| Window | Dates | Role |
|--------|-------|------|
| PIT / evaluation | **2015-01-01 → 2025-12-31** | Official research corpus (`coverage.json`, price-quality run, universe audit) |
| Momentum warmup | **~2013-07-08 → start** | `lookback_days=252` + 1 session → `warmup_sessions=253` |
| Full Historical Research Ready (future) | **2013-07-08 → 2025-12-31** | `FULL_HISTORY_EVAL_START` in `app/norgate_trial/constants.py` |
| Norgate Trial / vendor validation | **2024-09-03 → 2025-12-31** | Construction GO only |

**Minimum window for Strategy Research:** keep
**2015-01-01 → 2025-12-31** with warmup from **2013-07-08**.

Why these dates are not arbitrary:

1. They are the project’s existing evaluation window.
2. 12-1 momentum cannot emit a valid first signal without 252 sessions of
   **pre-signal** adjusted history.
3. Robustness and out-of-sample splits (for example in-sample 2015–2019,
   OOS 2020–2025) are partitions **of this window**, not a shorter Trial.
4. Distinct regimes inside 2015–2025: 2015–16 energy, 2018 vol, 2020 COVID,
   2022 rate shock, 2023–25. The Trial overlap (~16 months) is one late
   regime only.
5. Identity and corporate-action cases the engine must eventually handle
   sit **outside** Trial: Spectra SE 2017, ESRX 2018, ATVI 2023, SQ→XYZ
   2025 (in-window), HAR 2017.

The Trial window remains valid for **vendor validation**, not for
Strategy Research.

---

## 8. Survivorship / PIT assessment

**Historical constituent membership** ≠ **current constituent list**.

| Source | Historical membership | Current list | Survivorship-free prices |
|--------|----------------------|--------------|--------------------------|
| fja05680 `sp500_historical.csv` | Unofficial reconstruction; used by `historical_sp500` | Not used for PIT | Membership only |
| `--universe current` | No | Yes | Survivorship-**biased** |
| Yahoo | No | De facto live tickers | No |
| Norgate Trial | UNKNOWN live | Current names resolve | No (depth) |
| Norgate Platinum `$SPX` | Documented daily as-of true/false from 1957 | Current constituents also present | Designed yes **if** delisted tape is complete; still **not official SPDJI** |
| Sharadar SP500 | Documented adds/removes since 1957 | Yes | Documented intent; **not official SPDJI** |

fja05680 stays **unofficial**. Norgate `$SPX` may later **cross-check** it
(protocol M1). It must not replace `sp500_constituent_memberships` in this
round, and it is not an official S&P Dow Jones feed.

---

## 9. Identity assessment

Ticker alone must never become canonical identity.

| Case | Yahoo | Norgate Trial | Norgate full | Sharadar (documented) |
|------|-------|---------------|--------------|------------------------|
| SQ → XYZ same security | Remaps series to XYZ (usable **after** Security Master continuity) | XYZ `assetid=2104402`; SQ NOT_FOUND (prepend) | Same prepend rule; expect **same** `assetid` — **not live-proven** on Platinum | Ticker-change ACTIONS + stable permaticker — **not live-proven** |
| SE Spectra ≠ Sea | Local `SE.csv` is Sea only | Sea live; Spectra suffix NOT_FOUND | Distinct `assetid`s expected via `SE-YYYYMM` vs `SE` — **not live-proven** | Distinct permatickers expected — **not live-proven** |
| ESRX ≠ CI | Local ESRX.csv exists through 2018-12-21; must not alias | Suffix NOT_FOUND on Trial | Own delisted series expected — **not live-proven** | Own permaticker expected — **not live-proven** |
| BRK.B / BF.B share class | Vendor symbols `BRK-B` / `BF-B`; PIT keeps `BRK.B` / `BF.B` | Not probed | UNKNOWN | UNKNOWN |
| Ticker recycle | Fails (HAR, SE, CCE, TEG) | Pre-window untestable | Suffix + `assetid` is the documented mechanism | permaticker is the documented mechanism |

**All candidates still require this repo’s Security Master** to map
PIT ticker + as-of onto a vendor key. Norgate cannot answer “what ticker
was this `assetid` in 2015?”

---

## 10. Corporate-action data assessment

Target accounting (not wired; not started this round):

```
Split:     qty × factor; price ÷ factor; average_price ÷ factor; cash unchanged
Dividend:  cash += qty × dividend
Merger:    explicit cash/share conversion terms
Delisting: known terminal proceeds if available
```

| Input | Yahoo | Norgate | Sharadar (documented) | CRSP (documented, unlicensed) |
|-------|-------|---------|------------------------|-------------------------------|
| Split factor | No | No event factor; boolean flag only | ACTIONS split | Yes (PERMNO events) |
| Dividend per share | No (embedded in Adj Close only) | Amount column if not TOTALRETURN | ACTIONS | Yes |
| Merger cash/share terms | No | **No** (FAQ) | PARTIAL/UNKNOWN | Typically yes |
| Delisting proceeds | No (close proxy) | **No** (FAQ); last bar | delist reason; proceeds UNKNOWN | Delisting returns (DLRET) |

**Do not infer events from adjusted prices.**

Norgate **cannot** by itself satisfy the merger and delisting-proceeds
clauses of the accounting contract. It **can** support signal TR and
unadjusted/split-adjusted marks. A later CA vendor (Sharadar ACTIONS or
CRSP) is required before accounting can apply real mergers.

---

## 11. Single-vendor vs multi-vendor

The project **requires four logical datasets**:

1. PIT universe
2. Security master / identity
3. Price tape
4. Corporate-action events

**One vendor cannot reliably provide all four** given the evidence:

- Norgate: strong (3) + vendor PIT cross-check (1, unofficial) + vendor
  `assetid` (2 as attribute) + **weak/absent (4)** for mergers/delist
  proceeds; **no ticker history**.
- Yahoo: only convenience (3) for live tickers.
- Sharadar: documented (3)+(4)+partial (1)+(2); **not live-proven**;
  license/cost UNKNOWN.
- CRSP: research-grade (1–4) class; **not obtainable** here.

Provider independence remains mandatory:

```
Provider data
    → provider-specific adapter
    → canonical domain model
    → research/backtest engine
```

The domain must not import `norgatedata` or yfinance.

---

## 12. Recommended canonical architecture

**Smallest architecture that can satisfy research requirements:**

```
PIT universe (canonical):
    unofficial fja05680 → sp500_constituent_memberships
    later: official SPDJI if licensed
    optional cross-check: Norgate $SPX / Sharadar SP500 (never silent replace)

Identity (canonical):
    Security / Listing / VendorMapping
    security_id stays internal
    VendorMapping: NORGATE_ASSETID | YAHOO_SYMBOL | SHARADAR_PERMATICKER
    SEC CIK as evidence only

Prices (primary research tape):
    Norgate US Platinum  (unadjusted + TOTALRETURN + delisted)
    Yahoo / yfinance     (secondary validation for identity-safe listed names)

Corporate actions:
    Norgate Dividend column + capital-event flags = PARTIAL only
    Merger terms / delisting proceeds: separate feed (Sharadar ACTIONS or CRSP)
    until then: UNRESOLVED, last-close proxy documented

Canonical domain:
    Security
    Listing
    VendorMapping
    MarketBar          (roles via PriceSemantics, not vendor names)
    CorporateAction    (explicit events only)
```

**Why.** Platinum is the only **practical** delisted + `assetid` + PIT
cross-check product already Trial-validated as a vendor class. It still
cannot replace Security Master, cannot provide merger terms, and is not
official S&P membership. Yahoo remains the current smoke tape and a
listed-name checksum. Sharadar is the Mac-native **fallback** if a
Windows NDU operations path is rejected, and the better **event-table**
candidate. CRSP remains the academic upgrade, not the next purchase.

**Not recommended:** single-vendor Norgate-native backtest (Option D);
promoting Trial to research tape; promoting fja05680 to official;
inferring splits from Adj Close.

---

## 13. Evidence and unknowns

### Evidence used

- Round 10 AAPL split fixture and `YAHOO_CURRENT_TAPE`
- Coverage audit `audit/market_data_coverage/coverage.json` (754 / 113)
- Live Trial JSON (Windows 11 ARM64, 2026-09-03)
- Official Norgate FAQ, packages, PyPI, EULA (fetched 2026-09-06)
- Official Sharadar/Nasdaq SEP public description (no API key)
- This Mac: `norgatedata` missing (2026-09-06); 607 Yahoo CSVs

### Explicit UNKNOWN (not guessed)

1. Platinum live presence of ATVI, Spectra-SE, HAR/Harman, ESRX, the 113
2. Whether Norgate `assetid` matches this repo on TKO vs WWE
3. BRK.A vs BRK.B as distinct Norgate `assetid`s
4. Live `$SPX` vs fja05680 disagreement rates
5. Sharadar ACTIONS cash/share merger fields and license class / price
6. Completeness of Norgate delisted S&P members 2015–2025
7. Whether any undocumented Norgate API exposes split **ratio** history
8. CRSP commercial cost (not licensed)

---

## 14. Files / probes added

| Path | Role |
|------|------|
| `docs/audit/HISTORICAL_DATA_SOURCE_ASSESSMENT.md` | This report |
| `audit/historical_data_assessment/capability_matrix.json` | Machine-readable matrix |
| `audit/historical_data_assessment/gates.json` | Gate snapshot |

No production adapter. No DB migration. No isolated live Norgate probe
(this Mac cannot query NDU). Smokes wrote only `/tmp/r11-*`.

---

## 15–17. Regression

| Check | Result |
|-------|--------|
| `pytest -q` | **500 passed** (2.38s) |
| Explicit smoke `--start 2023-01-01 --end 2024-03-31 --symbol AAPL MSFT NVDA AMD` | orders **8**, fills **8**, equity **$110,718.02**, commission **$55.88**, slippage **$111.67** |
| PIT smoke `--universe historical_sp500` same dates | orders **22**, fills **22**, equity **$108,513.07**, commission **$72.45**, slippage **$144.79** |

Expected values were **not** changed. Smoke path remains Yahoo/CSV.

---

## 18. Remaining blockers

1. No research-grade price tape for delisted / recycled PIT names (Yahoo
   holes; Platinum not ingested).
2. Accounting redesign still required; current tape cannot apply real CA.
3. No merger terms / true delisting proceeds from any connected source.
4. Norgate split **factor** events are not available; Option A is blocked
   without another CA feed.
5. Security Master still exceptions-only (716/754 UNRESOLVED in the
   coverage snapshot).
6. fja05680 membership remains unofficial.
7. NDU not accessible from this Mac.
8. `backtest_infrastructure_ready` remains false (CA not wired; research
   tape not constructed).
9. Phase 5 / Strategy Research must not start.

**Next round (not started):** dataset construction design / Platinum
coverage proof on a frozen sample — not Strategy Research.
