# Data Acquisition Decision (Round 12)

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

**Assessment and decision only.** No production engine, `market_bars`, PIT
schema, Yahoo data, accounting, Broker, or Strategy Research was changed.
Norgate was not introduced into the production pipeline. The Data Layer was
not implemented.

Assessment date: **2026-09-06**.

Prior evidence (not erased):

- [HISTORICAL_DATA_SOURCE_ASSESSMENT.md](HISTORICAL_DATA_SOURCE_ASSESSMENT.md) (Round 11)
- [HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md](HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md)
- [NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md)
- [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md)
- [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md)
- Round 10 domain contracts: `app/domain/price_semantics.py`,
  `app/domain/corporate_actions.py`

Machine-readable matrix:

- [`audit/data_acquisition_decision/capability_matrix.json`](../../audit/data_acquisition_decision/capability_matrix.json)

---

## Unambiguous answer

**No currently accessible source can satisfy the frozen research-data contract
for 2013-07-08 → 2025-12-31.**

Yahoo is the only operational tape on this Mac. It cannot provide raw OHLC,
explicit corporate-action events, canonical identity, PIT membership, or a
survivorship-free delisted universe.

Norgate Trial is vendor-validation only (2024-09-03 → 2025-12-31) and is not
reachable from this Mac.

Norgate Platinum and Sharadar are the only practical candidates for the
research window. Neither is operationally available to this project today.
Neither is a complete single-vendor solution even after purchase.

**Target architecture (CONDITIONAL GO), not an available implementation:**

```
Option C hybrid — provider-independent canonical model

Primary market data
    Norgate US Stocks Platinum
        SIGNAL     → TOTALRETURN Close
        MARK       → CAPITAL Close  (split-adjusted, not dividend-adjusted)
        EXECUTION  → next-session CAPITAL Open
        TERMINAL   → CAPITAL Close
        volume     → consolidated tape volume
    Fallback if Windows/NDU cannot be stood up:
        Sharadar SEP
            SIGNAL     → closeadj
            MARK       → close
            EXECUTION  → next-session open
            TERMINAL   → close
            volume     → SEP volume (split-adjusted; dollar-volume comparable)

Corporate actions
    Sharadar ACTIONS  (documented event table)
        split value      → CorporateAction.factor
        dividend value   → CorporateAction.amount on ex-date
        tickerchange     → listing occupancy evidence
        acquisition      → identity evidence only until terms are live-proven
    Norgate Dividend column + capital_event boolean = PARTIAL only
    Missing merger cash/share terms → UNRESOLVED (do not invent)
    Missing delisting proceeds     → last quoted close proxy (existing policy)

Identity
    Canonical: this project's Security Master (security_id)
    Vendor attributes: NORGATE_ASSETID and/or SHARADAR_PERMATICKER
    Evidence: SEC CIK
    Ticker is never canonical

PIT
    Canonical membership: unofficial fja05680 → sp500_constituent_memberships
    Cross-check: Norgate $SPX index_constituent_timeseries
                 and/or Sharadar SP500 (fundamentals bundle SKU)
    Never current constituent lists
    Never silent replace of fja05680
    Not official SPDJI

Cross-validation
    Yahoo / yfinance for identity-safe currently listed names only
```

**Smallest additional capability required before the Data Layer can start:**

1. A paid, delisted-capable price tape covering **2013-07-08 → 2025-12-31**
   with a stable vendor ID — Norgate US Platinum **or** Sharadar SEP.
2. If Norgate is chosen: a working Windows/NDU Python path (this Mac cannot
   query NDU natively).
3. An explicit corporate-action event table with split **factor** and dividend
   **amount** — Sharadar ACTIONS is the documented candidate among practical
   vendors. Norgate cannot supply this.
4. A frozen coverage proof of the known identity cases (below) before any
   production ingest.

Merger cash/share terms remain a **mandatory unresolved gap** even after (1–4).
Until live-proven, acquisitions stay `UNRESOLVED`. CRSP is the documented
research-grade source for those terms and for delisting returns (`DLRET`).
Do not invent terms.

---

## Gates (do not collapse)

| Gate | Meaning | Status |
|------|---------|--------|
| Round 12 assessment | Decision document and matrix complete | **true** |
| Data source selected | An operational source is licensed and reachable | **false** (target named; not available) |
| Data architecture selected | Option C hybrid specified | **true** (conditional) |
| Data Layer implementation | Canonical research tape construction | **false** (not started) |
| Vendor validation | Trial window 2024-09-03 → 2025-12-31 | **true** (not re-run; not research tape) |
| Construction readiness | May continue infrastructure design | **true** |
| Research readiness | Scientifically valid Strategy Research | **false** |
| `backtest_infrastructure_ready` | Research tape + CA wiring + acceptance tests | **false** |

`full_historical_research_ready` remains **false**. Phase 5 remains
**NOT STARTED**.

---

## 1. Frozen contracts (not re-litigated)

### 1.1 Research window

| Window | Dates | Role |
|--------|-------|------|
| Evaluation / PIT | **2015-01-01 → 2025-12-31** | Official research corpus |
| Momentum warmup | **~2013-07-08** | `lookback_days=252` + 1 session → 253 sessions |
| Full Historical Research Ready | **2013-07-08 → 2025-12-31** | Required tape span |
| Norgate Trial | **2024-09-03 → 2025-12-31** | Vendor validation only |

The Trial window must **not** be used as the Strategy Research dataset.

### 1.2 Price roles (`PriceSemantics`)

| Role | Field | Session |
|------|-------|---------|
| SIGNAL | total-return / `adjusted_close` | as-of bar |
| EXECUTION | OPEN | next session |
| MARK | CLOSE | as-of bar |
| TERMINAL | CLOSE | last quoted; no slippage |

Price semantics must be explicitly documented on the loaded tape.
Never infer corporate actions from adjusted prices
(`infer_actions_from_prices` returns empty).

### 1.3 Corporate actions (`CorporateAction`)

| Event | Required input | Accounting |
|-------|----------------|------------|
| Split / reverse split | `factor > 0` | qty × factor; price ÷ factor; average_price ÷ factor; cash unchanged |
| Cash dividend | amount per share | cash += qty × amount on **ex-date** |
| Merger / acquisition | explicit cash-per-share and/or share conversion | missing terms → **UNRESOLVED** |
| Delisting | known proceeds if available | else last quoted close as **proxy** only |

Adjusted Close is not a cash ledger.

### 1.4 Identity

Canonical model: `Security → Listing → Ticker`. Runtime key is `security_id`.
Vendor IDs (`assetid`, `permaticker`, `PERMNO`) are attributes, not replacements.

Required outcomes:

| Case | Required outcome |
|------|------------------|
| SQ → XYZ | same security, same `position_key` |
| Spectra SE → Sea | different securities |
| ESRX → CI | different securities; do not alias to acquirer |
| BRK.B / BF.B | distinct share classes |
| Ticker recycle | distinct listing / security according to evidence |

### 1.5 PIT / survivorship

Must reconstruct membership as known on date D. Current constituent lists are
forbidden as the research universe. `historical_sp500` from unofficial
fja05680 remains unofficial. Norgate `$SPX` / Sharadar SP500 may later
cross-check it. They are not official SPDJI membership.

---

## 2. Repository inspection (read-only)

Inspected 2026-09-06. Production code was not modified.

### 2.1 Canonical domain

| Artifact | What it freezes |
|----------|-----------------|
| `app/domain/models/market_bar.py` | Daily OHLCV + optional `adjusted_close`. No CA fields. Yahoo Close is split-adjusted, not raw. |
| `app/domain/price_semantics.py` | Role map + `YAHOO_CURRENT_TAPE` capabilities (no raw OHLC, no events, last-close delist proxy). |
| `app/domain/models/corporate_action.py` | Event types, `factor`, `amount`, identity keys, `UNRESOLVED`. |
| `app/domain/corporate_actions.py` | Pure accounting. `EmptyCorporateActionProvider` is production. |
| `app/domain/models/security.py` | `security_id` / `seed_key`. Schemes today: `listing`, `yahoo` only. |
| `app/domain/models/listing.py` | Occupancy `[valid_from, valid_to)`. Recycled tickers are distinct listings. |
| `app/domain/models/identity.py` | `IdentityRef`, `PositionKey`. Ticker is never the booking key. |
| `app/security_master/identity_resolver.py` | Catalog resolver; does not mint unknown securities. |
| `app/security_master/vendor.py` | Listing ticker → Yahoo vendor symbol. No Norgate/Sharadar scheme yet. |
| `app/universe/interface.py` | `get_symbols(as_of)` half-open membership. |
| `app/universe/providers/query.py` | `historical_sp500` = PIT; `current` = survivorship-biased. |
| `app/data/providers/historical.py` | yfinance → CSV. Production price path. |
| `app/norgate_trial/` | Isolated trial client. Not a production adapter. |

### 2.2 Tests that the Data Layer must not weaken

Price semantics, identity, PIT, and corporate actions already have unit and
backtest tests (`tests/unit/domain/test_price_semantics.py`,
`test_corporate_actions.py`, `test_identity*.py`, `test_listing.py`,
`tests/backtest/test_identity_boundary.py`, `test_warmup_contract.py`,
`test_as_of_boundary.py`, universe/PIT tests). Round 12 does not change them.

### 2.3 Current operational tape

Production remains:

```
yfinance auto_adjust=False → data/raw/{SYMBOL}.csv → PostgreSQL market_bars
Universe: unofficial fja05680 intervals
Corporate actions: EmptyCorporateActionProvider
Identity: exceptions-only Security Master
```

That baseline is preserved.

---

## 3. Four evidence classes

Every important capability is classified on four axes. Do not collapse them.

| Class | Meaning |
|-------|---------|
| **A. Contractual** | What this project's domain requires. |
| **B. Vendor documented** | What public vendor documentation claims. |
| **C. Live-proven** | What this project has queried and verified. |
| **D. Project operational** | What this project can access and use **today**. |

Example that must not be collapsed:

> Norgate Platinum documents historical `$SPX` constituents (B).
> This project has not live-queried Platinum membership (not C).
> This Mac cannot access NDU (not D).

Matrix cells below are the **combined** research-usefulness rating.
The evidence column states which class the rating rests on.
`DOCUMENTED` in evidence never silently becomes live operational availability.

---

## 4. Capability matrix

Every cell is exactly one of: **SUPPORTED**, **PARTIAL**, **UNSUPPORTED**,
**UNKNOWN**.

Evidence notes may add **DOCUMENTED** and/or **LIVE-PROVEN** and always state
access (D).

Column notes:

- **Yahoo** — current production tape (`YAHOO_CURRENT_TAPE`). Live-proven on
  this project for listed CSV semantics (Round 10 AAPL fixture).
- **Norgate Trial** — 2024-09-03 → 2025-12-31. Live-proven on Windows 11 ARM64
  (2026-09-03 probe). Not reachable from this Mac (2026-09-06).
- **Norgate Platinum** — documented full-history class (to 1990, delisted,
  historical constituents). **Not live-proven** on Platinum. Trial ≠ Platinum.
- **Sharadar** — SEP / ACTIONS / TICKERS / SP500 public documentation
  (Nasdaq Data Link, Sharadar blog, QuantRocket, community schema).
  **Not live-queried.** No credentials in this environment.
- **CRSP** — documented research-grade US stock database. **Not licensed.
  Access unknown.** Candidate only.

| Capability | Yahoo | Norgate Trial | Norgate Platinum | Sharadar | CRSP |
|------------|-------|---------------|------------------|----------|------|
| Historical OHLC | SUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Raw OHLC | UNSUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Split-adjusted OHLC | SUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Total-return series | PARTIAL | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Split event factor | UNSUPPORTED | UNKNOWN | UNSUPPORTED | SUPPORTED | SUPPORTED |
| Dividend amount | UNSUPPORTED | PARTIAL | PARTIAL | SUPPORTED | SUPPORTED |
| Merger cash terms | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNKNOWN | PARTIAL |
| Merger share terms | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNKNOWN | PARTIAL |
| Delisting proceeds | UNSUPPORTED | PARTIAL | PARTIAL | UNKNOWN | SUPPORTED |
| Security identity | UNSUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Stable vendor ID | UNSUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Ticker history | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | SUPPORTED | SUPPORTED |
| Share classes | PARTIAL | UNKNOWN | UNKNOWN | PARTIAL | SUPPORTED |
| Historical constituents | UNSUPPORTED | UNKNOWN | SUPPORTED | PARTIAL | SUPPORTED |
| PIT membership | UNSUPPORTED | UNKNOWN | SUPPORTED | PARTIAL | SUPPORTED |
| Delisted securities | UNSUPPORTED | PARTIAL | SUPPORTED | SUPPORTED | SUPPORTED |
| Survivorship-free | UNSUPPORTED | UNSUPPORTED | PARTIAL | PARTIAL | SUPPORTED |
| Historical depth | PARTIAL | UNSUPPORTED | SUPPORTED | SUPPORTED | SUPPORTED |
| Corrections / revisions | PARTIAL | PARTIAL | PARTIAL | PARTIAL | SUPPORTED |
| Access available to this project | SUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED | UNSUPPORTED |
| Licensing suitability | PARTIAL | PARTIAL | PARTIAL | UNKNOWN | UNKNOWN |

### 4.1 Evidence for each capability

#### Historical OHLC

| Source | Status | A/B/C/D | Evidence |
|--------|--------|---------|----------|
| Yahoo | SUPPORTED | C+D | Local listed CSVs have daily OHLC. Semantics are split-adjusted, not raw. |
| Norgate Trial | PARTIAL | C (Windows) / D fail | Live listed names from 2024-09-03. Pre-window absent. |
| Norgate Platinum | SUPPORTED | B only | Documented daily OHLC to 1990. Not live-proven here. |
| Sharadar | SUPPORTED | B only | SEP documents OHLCV from 1998, active + delisted. DOCUMENTED. |
| CRSP | SUPPORTED | B only | Daily US stock OHLC documented. Not licensed. |

#### Raw OHLC

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | UNSUPPORTED | Round 10 AAPL 4-for-1: Close stays ~$125 across split. |
| Norgate Trial | PARTIAL | `StockPriceAdjustmentType.NONE` + Unadjusted Close documented; Trial used a 3-bar limit, not a full unadjusted tape proof. |
| Norgate Platinum | SUPPORTED | Documented NONE / Unadjusted Close / `unadjusted_close_timeseries`. DOCUMENTED, not live-proven. |
| Sharadar | SUPPORTED | Documented `closeunadj`. Unadjusted OHL imputed as `Open * CloseUnadj / Close`. DOCUMENTED. |
| CRSP | SUPPORTED | Documented unadjusted prices. |

#### Split-adjusted OHLC

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | SUPPORTED | Close is split-adjusted, not dividend-adjusted. Live-proven. |
| Norgate Trial | PARTIAL | CAPITAL mode documented; 2-year depth. |
| Norgate Platinum | SUPPORTED | CAPITAL / CAPITALSPECIAL documented. |
| Sharadar | SUPPORTED | SEP `open/high/low/close` split-adjusted, not cash-dividend or spinoff adjusted. DOCUMENTED. |
| CRSP | SUPPORTED | Adjustment factors documented in distributions. |

#### Total-return series

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | PARTIAL | `adjusted_close` = split + dividend. No separate TR named series. Live-proven as Adj Close. |
| Norgate Trial | PARTIAL | TOTALRETURN documented; 2-year only. |
| Norgate Platinum | SUPPORTED | TOTALRETURN is the default `price_timeseries` mode. DOCUMENTED. |
| Sharadar | SUPPORTED | `closeadj` = splits + cash dividends + spinoffs. Spinoff method = sell spinoff at open, buy parent at open. DOCUMENTED. |
| CRSP | SUPPORTED | `RET` holding-period return including dividends. DOCUMENTED. |

#### Split event factor

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | UNSUPPORTED | No event table on stored tape. Must not infer from prices. |
| Norgate Trial | UNKNOWN | Split event API not live-probed on Trial artifacts. |
| Norgate Platinum | UNSUPPORTED | FAQ: “Do you provide details on corporate action events such as splits and dividends? **No, not directly.**” `capital_event_timeseries` is boolean 1/0 mixing splits, reverse splits, bonus issues, stock dividends, and complex reorganizations. No factor field. Inferring factor from unadjusted vs adjusted prices is forbidden. |
| Sharadar | SUPPORTED | ACTIONS documents `action=split` and a numeric `value`. Sharadar's own adjustment blog defines split ratio as new/old float (e.g. 3-for-2 → 1.5). This is DOCUMENTED mapping to `factor`, **not live-proven**. Completeness of every split in 2013–2025 is UNKNOWN. |
| CRSP | SUPPORTED | Distribution file `FACSHR` / share factors. DOCUMENTED. |

Round 11 called Norgate Platinum split events **PARTIAL**. Round 12 tightens
that to **UNSUPPORTED** for the **factor** the accounting contract requires.
The boolean flag remains available; it cannot populate `CorporateAction.factor`.

#### Dividend amount

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | UNSUPPORTED | Embedded in Adj Close only. |
| Norgate Trial | PARTIAL | Dividend column documented when adjustment is not TOTALRETURN. Not live-proven on Trial. Entitlement = day **before** ex-date. |
| Norgate Platinum | PARTIAL | Same column rules. TOTALRETURN hides the column. Not a dated event table with pay vs ex-date. Ordinary vs special depends on CAPITAL vs CAPITALSPECIAL. |
| Sharadar | SUPPORTED | ACTIONS documents dividends; `value` is the amount in public column lists. DOCUMENTED, not live-proven. Cash vs stock dividend action enum must be confirmed live. |
| CRSP | SUPPORTED | `DIVAMT` per distribution. DOCUMENTED. |

#### Merger cash terms / merger share terms

| Source | Cash | Share | Evidence |
|--------|------|-------|----------|
| Yahoo | UNSUPPORTED | UNSUPPORTED | No terms. |
| Norgate Trial | UNSUPPORTED | UNSUPPORTED | FAQ identity rules only. |
| Norgate Platinum | UNSUPPORTED | UNSUPPORTED | FAQ: surviving-entity `assetid` rules; “there is no single value that could be supplied consistently for every event.” Explicitly no cash/share conversion terms. |
| Sharadar | UNKNOWN | UNKNOWN | ACTIONS marketing lists **acquisitions**. Public columns are `date, action, ticker, name, value, contraticker, contraname`. Counterparty identity is documented. Whether `value` is cash-per-share, a conversion ratio, both, or often null is **not specified in public docs** and was **not live-queried**. Do not convert “acquisitions exist” into “merger terms supported.” |
| CRSP | PARTIAL | PARTIAL | Distributions and delists document cash amounts, new PERMNO (`NWPERM`), and conversion-class events. Completeness of every cash/share combo in this project's cases (ATVI, ESRX) is not proven here. DOCUMENTED class, not live-proven. |

#### Delisting proceeds

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | UNSUPPORTED | Last-close proxy only (`known_delisting_last_close_proxy`). |
| Norgate Trial | PARTIAL | In-window last bar possible; pre-window suffixes NOT_FOUND. FAQ: no delisting return. |
| Norgate Platinum | PARTIAL | Last traded bar + `-YYYYMM` + `last_quoted_date`. FAQ: **no delisting return**, no delist reason. Matches this repo's last-close **proxy**. |
| Sharadar | UNKNOWN | Marketing lists **delist reasons**. Proceeds / DLRET-class fields are not in the public ACTIONS column list. Not live-proven. |
| CRSP | SUPPORTED | `DLRET`, `DLAMT`, `DLPRC` documented. Not licensed. |

#### Security identity / stable vendor ID

| Source | Identity | Stable ID | Evidence |
|--------|----------|-----------|----------|
| Yahoo | UNSUPPORTED | UNSUPPORTED | Ticker-keyed. Remaps SQ history onto XYZ. Recycles SE/HAR. |
| Norgate Trial | PARTIAL | PARTIAL | Live `assetid` for in-window listed (GME `124739`, XYZ `2104402`, Sea `2326776`, TKO `144819`, GEN `146955`, RVTY `130027`). Pre-window occupancies untestable. |
| Norgate Platinum | SUPPORTED | SUPPORTED | Integer `assetid` survives ticker change, exchange move, delisting. Store as `NORGATE_ASSETID`. Never replace `security_id`. DOCUMENTED. Completeness of the 113 UNKNOWN. |
| Sharadar | SUPPORTED | SUPPORTED | Documented unchanging `permaticker`. Public TICKERS text calls it an identifier for an **issuer** — whether share classes always get distinct permatickers is UNKNOWN until live-proven. DOCUMENTED. |
| CRSP | SUPPORTED | SUPPORTED | `PERMNO` (issue) and `PERMCO` (company). DOCUMENTED gold standard. |

#### Ticker history

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | UNSUPPORTED | History prepended onto current ticker. |
| Norgate Trial | UNSUPPORTED | Official FAQ: prior symbols are **not** provided. SQ NOT_FOUND; series on XYZ. |
| Norgate Platinum | UNSUPPORTED | Same FAQ. `norgatedata.symbol(assetid)` returns the **current** symbol only. Occupancy mapping remains this project's Security Master (PIT ticker + as-of → current or `TICKER-YYYYMM`). |
| Sharadar | SUPPORTED | ACTIONS documents ticker changes; TICKERS `relatedtickers` documents prior ticker and alternative share classes. DOCUMENTED, not live-proven. |
| CRSP | SUPPORTED | Name history file. DOCUMENTED. |

#### Share classes

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | PARTIAL | Vendor symbols `BRK-B` / `BF-B` exist locally; PIT keeps `BRK.B` / `BF.B`. Not a share-class master. |
| Norgate Trial | UNKNOWN | Sea name included “Class A ADR”. BRK.B vs BRK.A not live-tested. |
| Norgate Platinum | UNKNOWN | Distinct listings should have distinct `assetid`s; not live-proven. No CIK field. |
| Sharadar | PARTIAL | Community TICKERS usage includes `Domestic Common Stock Primary Class` / `Secondary Class` and `relatedtickers` for alternative classes. BRK.B vs BF.B not live-proven. Issuer-level permaticker wording is a residual risk. |
| CRSP | SUPPORTED | Distinct PERMNOs for Class A vs Class B. DOCUMENTED. |

#### Historical constituents / PIT membership

| Source | Constituents | PIT as-of | Evidence |
|--------|--------------|-----------|----------|
| Yahoo | UNSUPPORTED | UNSUPPORTED | Not a constituent feed. |
| Norgate Trial | UNKNOWN | UNKNOWN | SKU claims historical constituents at Trial depth; frozen 37-row probe did not dump `$SPX` membership. |
| Norgate Platinum | SUPPORTED | SUPPORTED | `$SPX` from Mar 1957. `index_constituent_timeseries(symbol, 'S&P 500' or '$SPX')` true/false as-of. Watchlists are **not** PIT. Temporary inclusions **not** included. No announcement dates. **Not official SPDJI.** DOCUMENTED, not live-proven on Platinum. |
| Sharadar | PARTIAL | PARTIAL | QuantRocket: S&P 500 additions/removals since 1957, `get_sharadar_sp500_reindexed_like`. **SKU caveat (Round 12):** Nasdaq SEP-only tables are SEP, ACTIONS, TICKERS, METRICS, INDICATORS — **no SP500**. QuantRocket pricing lists SP500 inside the **US Equities / fundamentals bundle**. Buying SEP-only may not include membership. **Not official SPDJI.** Not live-proven. |
| CRSP | SUPPORTED | SUPPORTED | `dsp500list` / `dsp500list_v2` membership intervals. Still not a substitute for a separately licensed SPDJI product, but it is the academic standard. DOCUMENTED. Not licensed here. |

#### Delisted securities / survivorship-free / historical depth

| Source | Delisted | Survivorship-free | Depth vs 2013-07-08 → 2025-12-31 |
|--------|----------|-------------------|----------------------------------|
| Yahoo | UNSUPPORTED | UNSUPPORTED | PARTIAL listed local files cover the window; 150 PIT names missing; 68 acquired/delisted of the 113 have no safe Yahoo series. |
| Norgate Trial | PARTIAL in-window | UNSUPPORTED | UNSUPPORTED vs required window. Pre-window delists NOT_FOUND. |
| Norgate Platinum | SUPPORTED (documented class) | PARTIAL | SUPPORTED (to 1990). Completeness of every S&P dropout / the 113 is UNKNOWN until a Platinum coverage proof. Membership not official SPDJI. |
| Sharadar | SUPPORTED (documented 20k+ active+delisted from 1998) | PARTIAL | SUPPORTED vs window (1998+). Completeness UNKNOWN. SP500 SKU caveat above. |
| CRSP | SUPPORTED | SUPPORTED | SUPPORTED (NYSE 1925; NASDAQ 1972). Not licensed. |

#### Corrections / revisions

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | PARTIAL | History is restated; no revision log on the stored CSV. |
| Norgate Trial / Platinum | PARTIAL | FAQ: database is **not** static; corrections applied continuously **without notification** (trades, dividends, surviving-entity determination). No revision table. |
| Sharadar | PARTIAL | `lastupdated` documented on SEP. No public revision-history API inspected here. |
| CRSP | SUPPORTED | Documented research-grade distribution with documented file versions. Not licensed. |

#### Access available to this project (D)

| Source | Status | Evidence (2026-09-06) |
|--------|--------|------------------------|
| Yahoo | SUPPORTED | yfinance + local CSVs + `market_bars`. Production path. |
| Norgate Trial | UNSUPPORTED | This Mac: `norgatedata` not installed; NDU not present. Prior Windows Trial evidence preserved. Trial depth is also insufficient for research. |
| Norgate Platinum | UNSUPPORTED | No paid Platinum subscription in this project. NDU Windows-only. Python must run **inside** the Windows environment (official PyPI: Mac may use a Windows VM; native Mac/Linux is “medium-term”). |
| Sharadar | UNSUPPORTED | `SHARADAR_API_KEY` / Nasdaq Data Link / Quandl credentials absent. Probe scripts already record `sharadar_sep: NOT EXECUTED`. |
| CRSP | UNSUPPORTED | No WRDS/CRSP license. Availability to this project unknown. |

#### Licensing suitability

| Source | Status | Evidence |
|--------|--------|----------|
| Yahoo | PARTIAL | Informal research use of yfinance. Not a licensed research tape. Redistribution of Yahoo content is constrained. |
| Norgate Trial | PARTIAL | Personal use; content deleted when trial ends; Derived Data (backtest statistics) may be retained. |
| Norgate Platinum | PARTIAL | Personal use only (individual trading/research/academic). **No commercial license.** Two personal machines. USD **630 / 12 months** public (stockmarketpackages.php, 2026-09-06). S&P index data reproduction restricted by SPDJI clause. On expiry: delete Content; retain Derived Data. Suitable for **personal research** if that is the project's use; **unsuitable** if the project later needs commercial/live-trading vendor redistribution. |
| Sharadar | UNKNOWN | QuantRocket pricing is **login-gated**. Sold as a **bundle of stock prices and fundamentals**; professional users must purchase from Nasdaq Data Link. Public third-party ranges exist and are **not** treated as a quote. Professional vs non-professional license applies. Cost and exact SKU (SEP-only vs US Equities bundle) are UNKNOWN until a written quote. |
| CRSP | UNKNOWN | Institutional / WRDS-class. Not a self-serve checkout. Cost UNKNOWN. |

---

## 5. Sharadar assessment (documented vs live)

**Live operational capability: UNKNOWN / NOT LIVE-PROVEN.**
No credentials. No API call was made. No sample row was downloaded.

### 5.1 Product shape (documented)

Nasdaq Data Link **SEP** product tables (public page):

- `SHARADAR/SEP` — daily prices
- `SHARADAR/ACTIONS` — corporate actions
- `SHARADAR/TICKERS` — reference
- `SHARADAR/METRICS`
- `SHARADAR/INDICATORS` — column dictionary (API-key gated)

Core US Equities / QuantRocket **US Equities Bundle** additionally documents:

- `SHARADAR/SP500` — S&P 500 additions/removals since 1957
- `SHARADAR/SF1` — fundamentals (PIT / as-reported; not required for prices)
- `SHARADAR/EVENTS` — 8-K events (not a substitute for ACTIONS)

**Round 12 SKU finding:** historical S&P 500 membership is **not** listed among
SEP-only tables. Treat SP500 as a **bundle/fundamentals SKU** unless a quote
explicitly includes it.

### 5.2 SEP fields → domain

| Vendor field | Documented meaning | Domain target | Transform | Limitation |
|--------------|--------------------|---------------|-----------|------------|
| `open, high, low, close` | Split-adjusted; **not** cash-dividend or spinoff adjusted | MARK / EXECUTION Close/Open if Option B/C | Direct. **Do not re-apply split events.** | Same Yahoo Close class. |
| `closeunadj` | Unadjusted close | Raw close / Option A mark | Direct. Impute OHL: `OpenUnadj = Open * CloseUnadj / Close` | Unadjusted OHL not stored as columns. |
| `closeadj` | Split + cash dividend + spinoff total-return close | SIGNAL | Direct | Spinoff TR method is vendor-specific (open-to-open). |
| `volume` | Split-adjusted volume | `MarketBar.volume` | Dollar volume `close * volume` remains comparable. Tape volume = `Volume * Close / CloseUnadj` | Do not mix CloseAdj into volume. |
| `ticker, date, lastupdated` | Keys / revision stamp | Join + freshness | Join through Security Master, not ticker alone | Ticker recycles still need occupancy. |

History: **1998 → present**, covering 2013-07-08 → 2025-12-31. Coverage claimed
for 20,000+ active **and delisted** US names. Completeness of the project's 113
is UNKNOWN until live query.

### 5.3 ACTIONS → corporate-action contract

Public column list (community exports + DuckDB/Nasdaq examples):

```
date, action, ticker, name, value, contraticker, contraname
```

Documented / marketed action types include: splits, dividends, spinoffs,
acquisitions, delist reasons, ticker changes. Example API filter:
`action=split`.

| Contract need | Documented? | Live-proven? | Can it populate `CorporateAction`? |
|---------------|-------------|--------------|-------------------------------------|
| Split factor | YES — `action=split` + numeric `value`; adjustment blog defines new/old float | NO | **Conditionally yes** after a live schema/row proof (AAPL 4-for-1 `value=4` or equivalent). |
| Dividend amount | YES — dividends listed; `value` used as amount in public schemas | NO | **Conditionally yes** after confirming cash vs stock action labels and that `date` is ex-date. |
| Dividend economic date = ex-date | Implied by adjustment examples (AAPL 2014-08-07) | NO | Must be live-verified. Payment date is not in the public column list. |
| Merger cash-per-share | Acquisition **events** documented; cash field **not** documented | NO | **UNKNOWN**. If `value` is null or is not cash, remain UNRESOLVED. |
| Merger share conversion | `contraticker` identifies counterparty; ratio **not** documented | NO | **UNKNOWN**. |
| Delisting proceeds | Delist **reasons** marketed; proceeds not in public columns | NO | **UNKNOWN**. Last close remains the only contract-legal proxy. |
| Ticker history | tickerchange + `relatedtickers` | NO | **Conditionally yes** as occupancy evidence, still mapped through Security Master. |

**ACTIONS is the best documented event table among practical vendors.**
It is **not** yet proven to satisfy the merger clauses of the frozen
accounting contract.

### 5.4 Identity

| Field | Documented meaning | Domain |
|-------|--------------------|--------|
| `permaticker` | Unchanging Sharadar identifier | `SHARADAR_PERMATICKER` vendor attribute |
| `ticker` | Current / row ticker | Listing display; never canonical |
| `isdelisted` | Y/N | Status hint, not occupancy |
| `firstpricedate` / `lastpricedate` | Price observation bounds | Occupancy hints; firstpricedate is not necessarily IPO |
| `relatedtickers` | Prior ticker and alternative share classes | Occupancy / class evidence |
| `category` | Includes Domestic / Canadian / ADR; community extracts also use Primary/Secondary Class | Share-class hint |
| `secfilings` | URL containing CIK | Evidence only |

Permaticker does **not** replace `security_id`.

### 5.5 PIT / survivorship

- Delisted prices: documented intent, not live-proven completeness.
- S&P 500 membership: documented from 1957 **in the fundamentals/bundle SKU**,
  with as-of helpers in QuantRocket. Unofficial vs SPDJI.
- Current lists remain forbidden.

### 5.6 Access / license

| Question | Answer |
|----------|--------|
| Credentials in this environment | **No** |
| Mac-native API | **Yes** (documented REST / bulk tables) — unlike Norgate |
| Live query performed this round | **No** |
| Price | **UNKNOWN** (login-gated) |
| Professional vs personal | Professional must buy from Nasdaq Data Link (QuantRocket) |
| SP500 included in cheapest SEP SKU | **Unknown / probably no** — see SKU caveat |

---

## 6. Norgate Platinum field mapping

Do not rely on marketing language. Trial behavior is **not** Platinum coverage.

Sources: official FAQ (data-package-faq.php), packages page, PyPI
`norgatedata` 1.0.77, EULA, prior Windows Trial JSON.

### 6.1 Field → domain

| Vendor field | Semantic meaning | Required domain field | Transform | Limitations |
|--------------|------------------|-----------------------|-----------|-------------|
| `assetid` | Unchanging integer ID | `VendorMapping.NORGATE_ASSETID` | Store as attribute | Never replace `security_id`. `symbol(assetid)` returns **current** symbol only. |
| `price_timeseries(..., NONE)` OHLC | Unadjusted prints | Raw OHLC if Option A | Direct | Not live-proven on Platinum here. |
| `Unadjusted Close` / `unadjusted_close_timeseries` | Unadjusted close | Raw close / audit | Direct | Helper for Zipline; also a column on price timeseries. |
| `price_timeseries(..., CAPITAL)` OHLC | Adjusted for splits / bonus / rights; **not** ordinary dividends | MARK / EXECUTION if Option B/C | Direct. **Do not also apply split events.** | Matches Yahoo Close class more closely than NONE. |
| `price_timeseries(..., TOTALRETURN)` Close | Capital + special + ordinary dividends | SIGNAL | Direct | **Hides Dividend column.** Must not be used as mark or cash ledger. |
| Volume / Turnover | Consolidated tape, includes pre/after hours | `volume` | Direct | Not last-sale-only volume. |
| Dividend column | Amount on **entitlement date** (day before ex-date) | `CASH_DIVIDEND.amount` | Shift to ex-date for accounting | Hidden under TOTALRETURN. Ordinary vs special depends on CAPITAL vs CAPITALSPECIAL. Not a full event table. |
| `capital_event_timeseries` | Boolean 1/0 | **Cannot** populate `factor` | None | Mixes splits, reverse splits, bonus, stock dividends, complex reorgs. FAQ: no direct CA details. |
| `dividend_yield_timeseries` | Trailing 12m yield | None for accounting | Ignore for events | Not an event. |
| `index_constituent_timeseries(symbol, 'S&P 500' or '$SPX')` | True/false as-of | PIT **cross-check** | Map via Security Master | Not official SPDJI. No temp inclusions. No announcement dates. Watchlists are not PIT. Platinum+ only. |
| `first_quoted_date` / `last_quoted_date` | Quote bounds | Occupancy hints | Evidence only | Not ticker history. |
| Delisted suffix `-YYYYMM` | Last-known symbol occupancy | `vendor_symbol` | Parse; never fetch a recycled live ticker | History lives on last symbol (AOL example in FAQ). |
| `major_exchange_listed_timeseries` | Major vs OTC by date (from ~1990/2000) | Downlist vs true delist | Evidence | Not proceeds. |

### 6.2 What Platinum can and cannot feed

**Can (documented):** unadjusted and adjusted OHLC, TOTALRETURN, volume,
delisted securities as a product class, `assetid`, `$SPX` as-of membership,
history through 1990 (covers 2013–2025).

**Cannot:**

- split **factor** event table
- ticker history / prior symbols
- merger cash or share terms
- delisting return / reason
- official SPDJI membership
- proven completeness of ATVI, Spectra-SE, HAR, ESRX, or the 113

**Must not claim** Platinum currently contains those specific securities.
That remains a future coverage proof.

### 6.3 Access

NDU is Windows-only. This Mac cannot query it. A Windows VM with Python
**inside the VM** is the documented Mac path. WSL2 requires mirrored
networking. There is no REST API and no rate limit (local DB). Corrections
arrive without notification. Database inaccessible after subscription expiry.

---

## 7. Candidate architecture verdicts

| Architecture | Verdict | Why |
|--------------|---------|-----|
| **Option A** — Unadjusted OHLC + separate CA feed + PIT + Security Master | **CONDITIONAL GO** (blocked today) | Cleanest audit trail and matches `qty × factor` on a raw tape. Blocked because (1) Yahoo is not raw, (2) Norgate has no split-factor events, (3) Sharadar ACTIONS split factor is documented but not live-proven, (4) no operational CA feed. |
| **Option B** — Split-adjusted OHLC + separate CA feed + PIT + SM | **CONDITIONAL GO** with a hard rule | Matches Yahoo Close and Sharadar SEP OHLC / Norgate CAPITAL. **Do not re-apply splits** or they double-count. Dividends may still credit cash because Close is not dividend-adjusted. Easy to get wrong. |
| **Option C** — Vendor TR + Close + separate CA events + PIT + SM | **CONDITIONAL GO — recommended** | Matches frozen `PriceSemantics`: SIGNAL=TR, MARK=CLOSE, EXECUTION=OPEN, accounting=events. Still needs a real event source, especially for mergers. |
| **Option D** — Vendor-native backtest dataset | **NO-GO** | Provider independence is mandatory. The engine must run on this project's canonical model, not Norgate+Zipline or Sharadar+QuantRocket. Surviving-entity rules may disagree with TKO / ESRX / LLL. Lowest auditability. |

### Per-source GO / CONDITIONAL GO / NO-GO

| Candidate | As research primary | As secondary / role | Verdict |
|-----------|---------------------|---------------------|---------|
| Yahoo | NO-GO | Checksum / smoke for identity-safe listed names | **GO as secondary only** |
| Norgate Trial | NO-GO | Vendor validation artifact | **NO-GO** for research tape |
| Norgate Platinum (alone) | NO-GO | Prices + PIT cross-check + `assetid` | **CONDITIONAL GO** for those roles if NDU + subscription + coverage proof |
| Sharadar SEP+ACTIONS (alone) | CONDITIONAL GO | Prices + events + permaticker; PIT only if SP500 SKU included | **CONDITIONAL GO** after credentials, license, live proof |
| CRSP | CONDITIONAL GO | Research-grade upgrade (PERMNO, DLRET, distributions, membership) | **NO-GO operationally** (no access). Keep as upgrade path. |
| fja05680 | NO-GO as official | Current canonical unofficial PIT | **Remain unofficial** |
| Multi-vendor Option C hybrid | CONDITIONAL GO | See §8 | **Recommended target** |

---

## 8. Recommended architecture

**Name:** Option C hybrid (provider-independent).

**Status:** CONDITIONAL GO. Not implementable until the smallest additional
capability in §11 is obtained.

| Role | Who supplies it | Notes |
|------|-----------------|-------|
| **Primary market data** | **Norgate US Stocks Platinum** | OHLC, volume, TOTALRETURN, CAPITAL Close, Unadjusted Close for audit, delisted class, history to 1990. |
| **Primary market data fallback** | **Sharadar SEP** | Use if Windows/NDU is rejected. `closeadj` / `close` / `open` / `closeunadj`. Mac-native. |
| **Corporate actions** | **Sharadar ACTIONS** | Splits and dividends (documented). Ticker changes. Acquisitions = identity evidence until terms are live-proven. |
| **Corporate actions (partial complement)** | Norgate Dividend column (non-TR modes) + capital-event **flag** | Flag is not a factor. Do not infer factors from prices. |
| **Identity (canonical)** | **This project's Security Master** | `security_id`. Listings with occupancy. |
| **Identity (vendor attributes)** | Norgate `assetid` and/or Sharadar `permaticker` | Plus SEC CIK as evidence. |
| **Ticker / listing history** | Security Master occupancy, fed by Sharadar tickerchange / relatedtickers when live-proven; Norgate **cannot** supply prior symbols | PIT ticker + as-of → vendor key. |
| **PIT (canonical)** | **Unofficial fja05680** → `sp500_constituent_memberships` | Do not promote to official. |
| **PIT (cross-check)** | Norgate `$SPX` `index_constituent_timeseries` and/or Sharadar SP500 (bundle SKU) | Disagreement report only. Never silent replace. |
| **Cross-validation prices** | **Yahoo** | Identity-safe currently listed names. Never recycle/delisted primary. |

### Why this split

1. The frozen signal/mark/execution split is already Option C.
2. Norgate is the only vendor this project has **live-proven as a class**
   (Trial) for delisted databases + `assetid`. Platinum is the documented
   product that covers 2013–2025.
3. Norgate **cannot** satisfy the split-factor or merger-terms clauses.
   Option A on Norgate alone is impossible without forbidden price inference.
4. Sharadar ACTIONS is the only practical documented event table with a split
   `value` and dividend `value`.
5. Sharadar is Mac-native; Norgate is not. The fallback exists because D
   (operational access) currently fails for both paid vendors — but for
   different reasons.
6. Identity and PIT stay inside this repo. Vendor IDs and vendor membership
   never become canonical.
7. Option D is rejected: the BacktestEngine must not become a Norgate or
   QuantRocket wrapper.

### Mapping onto canonical types (future Data Layer — not implemented)

```
Provider adapter
    → MarketBar (roles via PriceSemantics, vendor field documented)
    → CorporateAction (explicit events only; UNRESOLVED if terms missing)
    → VendorMapping (NORGATE_ASSETID | SHARADAR_PERMATICKER | YAHOO_SYMBOL)
    → Listing occupancy
    → UniverseProvider.get_symbols(as_of)
        → BacktestEngine
```

The domain must not import `norgatedata`, Nasdaq Data Link, or yfinance.

---

## 9. Alternatives considered

### Single-vendor Norgate Platinum

Rejected as a **complete** research dataset. Strong on prices, delisted class,
`assetid`, and PIT cross-check. Fatal gaps: no split factor, no ticker history,
no merger terms, no delisting proceeds, no Mac-native access, completeness of
required names unproven. CONDITIONAL GO only as the **price** leg.

### Single-vendor Sharadar

Stronger on the event table and ticker history; Mac-native. Rejected as an
immediate GO because: not live-proven, no credentials, license/cost UNKNOWN,
SP500 may require a larger bundle, merger terms UNKNOWN, permaticker
issuer-vs-issue ambiguity, completeness unproven. CONDITIONAL GO as
**fallback primary** and as the **CA** leg.

### Single-vendor Yahoo

Rejected. Smoke tape only. Known failures: recycle (SE, HAR), remap (SQ→XYZ
without occupancy), delisted holes, no events, no PIT.

### Single-vendor CRSP

Best documented match to the **entire** contract (PERMNO, FACSHR, DIVAMT,
DLRET, name history, index membership). Rejected as the next purchase because
access is not established. Remains the research-grade upgrade, especially for
merger economics and delisting proceeds.

### Option D vendor backtest engines

Rejected. Provider independence and auditability.

### Promoting Trial or fja05680

Rejected. Trial is the wrong window. fja05680 stays unofficial.

### Inferring splits from Adj Close / Unadjusted Close ratios

Rejected. Forbidden by Round 10 (`infer_actions_from_prices`).

---

## 10. Future coverage proof (acceptance sample)

Not a production migration. Not executed this round. This is the gate before
any chosen vendor is ingested.

For each case the Data Layer must answer seven questions:

1. Can the security be found?
2. Can the historical listing / occupancy be found?
3. Can historical prices for **2013-07-08 → 2025-12-31** (or the occupancy
   intersection) be retrieved?
4. Can identity be mapped without ticker guessing?
5. Can PIT membership be established on relevant as-of dates?
6. Can corporate actions be represented (or explicitly UNRESOLVED)?
7. Does the name remain in the research tape when currently delisted?

| Case | What must be true | Fail if |
|------|-------------------|---------|
| **SQ → XYZ** | Same `security_id` / `position_key`. Vendor ID stable across the 2025 ticker change. Prices continuous on the vendor key. SQ as a current ticker must not be required. | Two IDs for one Class A; or fetching SQ returns a different issuer. |
| **Spectra SE → Sea** | Two `security_id`s. Spectra occupancy (to 2017-02) ≠ Sea (from 2017-10). Distinct vendor IDs. Spectra prices are Spectra, not Sea. | Any join of the two series; Yahoo-style `SE.csv` overwrite. |
| **ESRX → CI** | ESRX remains its own security through 2018-12-21. CI is a different security. No acquirer alias. | ESRX bars served as CI, or position_key collapse. |
| **ATVI → Microsoft** | ATVI found as delisted occupancy (≈ ATVI-202310 on Norgate class). Prices through last trade. Acquisition terms explicit or **UNRESOLVED** — never invented. MSFT is not ATVI. | Alias to MSFT; invented cash/share terms. |
| **BRK.B vs BF.B** | Two listings, two securities (and distinct from Class A). Vendor IDs distinct. | Single ID or ticker-normalization collision (`BRK.B`/`BRK-B`). |
| **Ticker recycle** (HAR, SE, and a documented recycle such as the AOL/TWX FAQ class) | Distinct listings; live ticker must not fetch the dead occupancy. | Current-ticker contamination. |
| **Delisted security** (e.g. HAR, CELG, or in-window Trial-class name) | Retrievable by vendor ID / last symbol, not by recycled live ticker. Survives into the tape. Last close usable as terminal **proxy**; proceeds only if explicit. | Missing series dropped from the universe solely because Yahoo lacks it. |

PIT check (all cases that were S&P members): `UniverseProvider.get_symbols(as_of)`
includes the PIT ticker on dates inside membership and excludes it after
`end_date` (half-open). Vendor `$SPX` / Sharadar SP500 may disagree with
fja05680; disagreements are logged, not auto-merged.

---

## 11. MANDATORY UNRESOLVED GAPS

Do not force a GO. Each gap blocks `backtest_infrastructure_ready` and/or
honest merger accounting.

### G1. No operational research tape

| | |
|--|--|
| **Requirement** | Daily OHLC + TR + delisted coverage for 2013-07-08 → 2025-12-31. |
| **Evidence** | Yahoo holes (113 / recycle). Norgate/Sharadar/CRSP not accessible (D). |
| **Why it matters** | Strategy Research on Yahoo is survivorship-biased and identity-unsafe. |
| **Possible solution** | License Norgate Platinum (plus Windows/NDU) or Sharadar SEP. |
| **Acceptance test** | Coverage proof §10 questions 1–3 and 7 pass for the frozen sample. |

### G2. Split factor event table

| | |
|--|--|
| **Requirement** | Explicit `factor > 0` for splits and reverse splits. |
| **Evidence** | Norgate FAQ: no direct CA details; boolean flag only. Yahoo: none. Sharadar ACTIONS: documented `split`+`value`, not live-proven. |
| **Why it matters** | Option A accounting cannot run. Inferring factor from prices is forbidden. |
| **Possible solution** | Live-prove Sharadar ACTIONS split rows (AAPL 4-for-1). CRSP `FACSHR` if licensed. |
| **Acceptance test** | AAPL 2020-08-31 (and one reverse split) maps to `CorporateAction.factor` without reading Adj Close ratios. |

### G3. Merger cash and share terms

| | |
|--|--|
| **Requirement** | Explicit cash-per-share and/or conversion ratio, plus identity evidence. Else UNRESOLVED. |
| **Evidence** | Norgate: unsupported (FAQ). Sharadar: acquisition **rows** documented; term fields UNKNOWN. CRSP: documented class, unlicensed. |
| **Why it matters** | ATVI, ESRX-class, and 68 acquired/delisted names in the 113. Inventing terms would falsify terminal P&L. |
| **Possible solution** | Live-inspect Sharadar ACTIONS acquisition `value`/`contraticker`. If insufficient, CRSP distributions/delists or leave UNRESOLVED and document. |
| **Acceptance test** | ATVI and ESRX: either APPLIED with sourced terms, or UNRESOLVED with unchanged quantity — never a guessed ratio. |

### G4. Delisting proceeds

| | |
|--|--|
| **Requirement** | Known proceeds if available; else last quoted close proxy. |
| **Evidence** | Norgate: no delisting return. Sharadar proceeds UNKNOWN. CRSP `DLRET` documented, unlicensed. |
| **Why it matters** | Bankruptcy vs cash takeover vs OTC continuation are different economics. |
| **Possible solution** | Keep last-close proxy as the **documented** terminal policy until CRSP or a proven proceeds field exists. |
| **Acceptance test** | Delist path uses CLOSE, not Adj Close; missing terminal_price fails closed rather than inventing a print. |

### G5. Share-class identity

| | |
|--|--|
| **Requirement** | BRK.B / BF.B (and Class A) distinct. |
| **Evidence** | Not live-proven on Norgate Platinum or Sharadar. Yahoo symbol mapping exists but is not a master. CRSP PERMNO would distinguish. |
| **Why it matters** | Wrong class aliases distort both identity and prices. |
| **Possible solution** | Coverage proof rows for BRK.B, BRK.A, BF.B, BF.A on the chosen vendor ID. |
| **Acceptance test** | Four distinct `security_id`s (or documented two if a class is absent from the PIT universe) and distinct vendor IDs. |

### G6. Ticker / listing history

| | |
|--|--|
| **Requirement** | Historical occupancy: which ticker named this security on date D. |
| **Evidence** | Norgate: unsupported (FAQ). Sharadar tickerchange documented, not live. This repo's Security Master is still exceptions-only (716/754 UNRESOLVED in the coverage snapshot). |
| **Why it matters** | Recycle and ticker-change cases cannot be fetched safely by PIT ticker. |
| **Possible solution** | Author occupancy from Sharadar ACTIONS + SEC evidence; use Norgate last-symbol / `assetid` as the fetch key, not the PIT ticker. |
| **Acceptance test** | Spectra SE as-of 2016 does not resolve to Sea; SQ as-of 2024 and XYZ as-of 2026 share `security_id`. |

### G7. PIT completeness / unofficial membership

| | |
|--|--|
| **Requirement** | As-of S&P 500 membership for 2015–2025, survivorship-free. |
| **Evidence** | Canonical source is unofficial fja05680. Norgate `$SPX` and Sharadar SP500 are unofficial reconstructions; SP500 may need a Sharadar bundle SKU. No official SPDJI license. |
| **Why it matters** | Wrong membership is a different strategy than claimed. |
| **Possible solution** | Keep fja05680; add vendor cross-check diffs; optional later SPDJI license. |
| **Acceptance test** | Known join/leave dates match fja05680; vendor disagreements listed, not auto-applied. `--universe current` remains labeled survivorship-biased. |

### G8. Delisted coverage completeness

| | |
|--|--|
| **Requirement** | Prices for delisted PIT names, including the 68 acquired/delisted of the 113. |
| **Evidence** | Yahoo inadequate. Trial pre-window NOT_FOUND. Platinum/Sharadar completeness UNKNOWN. |
| **Why it matters** | Dropping missing names biases momentum upward. |
| **Possible solution** | Platinum or Sharadar coverage proof on the 113 + overlay occupancies. Missing names stay in the universe with a missing-data flag. |
| **Acceptance test** | ATVI, CELG, HAR/Harman, Spectra-SE retrieve bars; they are not replaced by acquirer or recycled live tickers. |

### G9. Licensing / access

| | |
|--|--|
| **Requirement** | A legally usable, reachable vendor for personal research. |
| **Evidence** | Norgate: personal-use EULA, Windows NDU, USD 630/year Platinum public. Sharadar: login-gated, SKU unclear. CRSP: unavailable. This Mac: neither paid vendor reachable. |
| **Why it matters** | Documented capability ≠ project access. |
| **Possible solution** | (a) Windows VM + Norgate Platinum, and/or (b) Sharadar quote for SEP+ACTIONS, plus SP500 if PIT cross-check is required from Sharadar. |
| **Acceptance test** | A bounded probe (not production ingest) returns assetid/permaticker and a 2013-07-08 bar for a listed control (e.g. AAPL) and one delisted sample. |

### G10. Dividend ex-date vs entitlement date

| | |
|--|--|
| **Requirement** | Cash dividend economic date = **ex-date**. |
| **Evidence** | Norgate Dividend column is **day before** ex-date. Sharadar date semantics not live-proven. |
| **Why it matters** | Off-by-one cash credits vs the frozen contract. |
| **Possible solution** | Adapter shifts Norgate entitlement → ex-date; verify Sharadar `date` live. |
| **Acceptance test** | A known ordinary dividend credits cash on ex-date, not on the prior close, and does not rewrite Close. |

---

## 12. Data Layer acceptance tests

These tests are the gate before `backtest_infrastructure_ready = true`.
They are **specified now**, not implemented as a production migration.

The chosen architecture must pass all of the following on a **frozen input
dataset** (vendor snapshot with a recorded as-of). Corrections without
notification (Norgate) imply the snapshot must be versioned by the project.

### 12.1 Price semantics

| Test | Expected |
|------|----------|
| Signal uses total-return field only | Momentum reads TOTALRETURN / `closeadj` / `adjusted_close`, never raw Close. |
| Execution uses next-session OPEN | Fill price is next bar open of the **mark** tape (CAPITAL / SEP `open`), never TR. |
| Mark uses CLOSE | Equity marks on Close of the mark tape, not Adj Close. |
| Terminal uses CLOSE, no slippage | Delist/liquidation uses last quoted close; slippage flag false. |
| Tape capabilities recorded | `TapeCapabilities` (or successor) states raw vs split-adjusted vs TR explicitly. |
| No double-counted splits | If the mark tape is split-adjusted, split events do not rescale marks again. |
| No TR in the cash ledger | Crediting dividends does not also mark on `closeadj`. |

### 12.2 Identity

| Test | Expected |
|------|----------|
| SQ → XYZ | Same `security_id` and `position_key`. |
| Spectra SE vs Sea | Different `security_id`s; Sea bars never used for Spectra occupancy. |
| ESRX vs CI | Different `security_id`s; no acquirer alias. |
| BRK.B vs BF.B | Distinct securities / listings. |
| Recycled ticker | Distinct listings; unknown occupancy does not merge. |
| Vendor ID is an attribute | `assetid` / `permaticker` stored; booking key remains `security_id`. |
| UNRESOLVED | No guessed `security_id`. |

### 12.3 PIT

| Test | Expected |
|------|----------|
| As-of membership | `get_symbols(D)` uses `[start, end)`. |
| Historical not current | A name that left before D is absent; a later addition is absent before its start. |
| `--universe current` | Still survivorship-biased and labeled as such. |
| fja05680 unofficial | Source metadata remains unofficial; vendor `$SPX` diffs are reports only. |

### 12.4 Survivorship

| Test | Expected |
|------|----------|
| Delisted remains available | ATVI-class names have bars through last trade when the vendor has them. |
| Missing prices ≠ dropped membership | A member without bars stays in the universe with a missing-data diagnostic. |
| Recycle-safe fetch | Live ticker is not used to fill a dead occupancy. |

### 12.5 Corporate actions

| Event | Expected resolution |
|-------|---------------------|
| Split | `factor` applied: qty × factor, prices ÷ factor, cash unchanged. |
| Reverse split | Same formula with `factor < 1`. |
| Dividend | `cash += qty × amount` on ex-date; qty unchanged; Close not rewritten. |
| Merger / acquisition | APPLIED only with explicit cash and/or share terms; otherwise **UNRESOLVED**. |
| Delisting | Last quoted close proxy unless proceeds are explicit; never invented. |
| Rename | Display ticker may change; `position_key` does not. |
| Inference | `infer_actions_from_prices` remains empty. |

### 12.6 Determinism

Same frozen input dataset must produce identical:

- orders
- fills
- accounting snapshots (cash, qty, average_price)
- CSV export (`fills.csv`, `orders.csv`, `equity_curve.csv`)

Run twice. Byte-or-decimal compare. Vendor live updates must not silently
change a frozen snapshot.

### 12.7 Regression baseline (must remain until a separate implementation round)

Until an approved implementation round changes the production tape:

| Check | Expected |
|-------|----------|
| `pytest -q` | **500 passed** |
| Explicit smoke `--start 2023-01-01 --end 2024-03-31 --symbol AAPL MSFT NVDA AMD` | orders **8**, fills **8**, equity **$110,718.02**, commission **$55.88**, slippage **$111.67** |
| PIT smoke `--universe historical_sp500` same dates | orders **22**, fills **22**, equity **$108,513.07**, commission **$72.45**, slippage **$144.79** |

Do **not** update expected values merely to make tests pass.

---

## 13. Smallest additional data capability / license

Because no currently accessible source satisfies the contract, the next
purchase is **not** Strategy Research. It is one of these, in order of
preference for this project's frozen contract:

**Path 1 (preferred price class, CONDITIONAL):**

1. Norgate US Stocks **Platinum** (public USD 630 / 12 months, personal use).
2. A Windows environment with NDU + `norgatedata` (VM on this Mac is acceptable
   per vendor docs; Python must run in that Windows environment).
3. Sharadar **ACTIONS** (and enough SEP/TICKERS to join events to
   permaticker) — written quote required; SKU must include ACTIONS.
4. Optional: Sharadar SP500 or rely on Norgate `$SPX` for PIT cross-check.

**Path 2 (if NDU is rejected):**

1. Sharadar US Equities bundle (or SEP+ACTIONS+TICKERS with an explicit
   statement whether SP500 is included).
2. Written license confirmation for personal research.
3. Live ACTIONS proof for split `value` and acquisition `value`.

**Path 3 (research-grade upgrade, not the next mandatory buy):**

CRSP US Stock via WRDS/commercial license — required only if merger terms and
true delisting proceeds must be APPLIED rather than UNRESOLVED / last-close
proxy.

Do **not** implement these capabilities in Round 12.

---

## 14. Round 12 regression

Production code was not modified in this round. Expected values were not
changed.

| Check | Result |
|-------|--------|
| `pytest -q` | **500 passed** (2.43s) |
| Explicit smoke `--start 2023-01-01 --end 2024-03-31 --symbol AAPL MSFT NVDA AMD` | orders **8**, fills **8**, equity **$110,718.02**, commission **$55.88**, slippage **$111.67** |
| PIT smoke `--universe historical_sp500` same dates | orders **22**, fills **22**, equity **$108,513.07**, commission **$72.45**, slippage **$144.79** |

Smokes wrote only `/tmp/r12-explicit` and `/tmp/r12-pit`. Smoke path remains
Yahoo/CSV.

Artifacts added (assessment only):

| Path | Role |
|------|------|
| `docs/audit/DATA_ACQUISITION_DECISION.md` | This decision |
| `audit/data_acquisition_decision/capability_matrix.json` | Machine-readable matrix |
| `audit/data_acquisition_decision/gates.json` | Gate snapshot |

No production adapter. No DB migration. No Norgate ingest. No Yahoo
replacement.

---

## 15. Status

```
round_12_assessment_complete = true
data_source_selected = not_operational — target: norgate_platinum_prices + sharadar_actions + internal_security_master + unofficial_fja05680_pit
data_architecture_selected = option_c_hybrid_conditional
data_layer_implementation_started = false
backtest_infrastructure_ready = false
research_ready = false
phase_5 = NOT_STARTED
```

**Final sentence.** Build the 2013-07-08 → 2025-12-31 research tape as an
Option C hybrid: Norgate Platinum (or Sharadar SEP if NDU cannot be stood up)
for prices, Sharadar ACTIONS for explicit events, this project's Security
Master for identity, unofficial fja05680 for PIT with vendor cross-check, and
Yahoo only as a listed-name checksum — and do not start that Data Layer until
the licenses and coverage proofs above exist, leaving merger terms UNRESOLVED
until they are live-proven rather than invented.
