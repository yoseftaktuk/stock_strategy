# Historical Market Data Source Research

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

This document records a Phase 4 investigation of historical US equity market-data
sources. It does **not** claim the pipeline is research-ready. No mass download
was performed. Security Master was not redesigned. The Backtest Engine was not
modified. Strategy Research was not started.

Prior evidence:

- [HISTORICAL_MARKET_DATA_COVERAGE.md](HISTORICAL_MARKET_DATA_COVERAGE.md)
- [SECURITY_MASTER_AUDIT.md](SECURITY_MASTER_AUDIT.md)
- [PRICE_QUALITY_VALIDATION.md](PRICE_QUALITY_VALIDATION.md)
- [HISTORICAL_UNIVERSE_AUDIT.md](HISTORICAL_UNIVERSE_AUDIT.md)
- [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md) (frozen-sample probe; Norgate not live-testable on this Mac)
- [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md) (14-section live-trial protocol, 2026-09-03 rewrite; not executed; **NOT TESTABLE** on this Mac)

Machine-readable coverage (offline; not regenerated in this step):

- [`audit/market_data_coverage/coverage.csv`](../../audit/market_data_coverage/coverage.csv)
- [`audit/market_data_coverage/coverage.json`](../../audit/market_data_coverage/coverage.json)
- [`audit/market_data_coverage/missing.csv`](../../audit/market_data_coverage/missing.csv)

Research date: **2026-09-02**. Price window required: **2015-01-01 → 2025-12-31**
inclusive, plus Momentum warm-up from typically **2013-07-08**.

---

## 1. Objective

Determine what is required to obtain point-in-time usable daily OHLCV plus
adjusted pricing for historical US equities in this project’s PIT universe,
including delisted securities and ticker changes, while preserving security
identity.

The question is not “which API can download tickers.” It is: which source (or
combination of sources) can supply identity-aware historical bars for names that
Yahoo cannot safely serve, so a survivorship-bias-aware backtest can be fed
without ticker contamination.

This investigation answers:

1. What the missing 113 actually are.
2. What market-data fields this codebase requires.
3. Which vendors can meet those requirements.
4. Whether one provider is enough.
5. What to acquire next — and what not to acquire yet.

---

## 2. Current coverage problem

PIT window 2015-01-01 → 2025-12-31. Source of membership: unofficial
[fja05680/sp500](https://github.com/fja05680/sp500) reconstruction. Official
S&P Dow Jones membership remains **UNCERTAIN**.

From [`coverage.json`](../../audit/market_data_coverage/coverage.json):

| Metric | Count |
|--------|-------|
| PIT securities with window overlap | 754 |
| Rebalance-encountered after warmup | 724 |
| Valid data | 604 |
| Partial | 8 |
| Unusable | 2 |
| Missing | 150 |
| Identity unresolved | 716 |
| Window listing CSV absent | 149 |
| Rebalance listing CSV absent | 129 |

These numbers are **not** “download 113 CSV files.” Some names are delisted,
ticker changes, recycled tickers, vendor-symbol differences, or identities that
Yahoo will not serve correctly.

Current local path:

- CSV cache under `data/raw/{SYMBOL}.csv`
- yfinance / `HISTORICAL` provider when a file is fetched
- PostgreSQL `market_bars` is what the backtest reads
- `OfflineMarketDataProvider` / CSV for offline runs
- `market_bars.stock_id` is still a ticker row, not `security_id`

Yahoo via yfinance was intentionally not used for a bulk fill of the 113 because
fetching the PIT ticker often returns a recycled instrument (`HAR`, `CCE`,
`TEG`, `PARA`). That policy remains correct.

### 2.1 Reconciliation of 129 vs 113 vs 149

[`missing.csv`](../../audit/market_data_coverage/missing.csv) has **149** rows
(window listing-CSV absent).

| Slice | Count | Definition |
|-------|-------|------------|
| Window listing-CSV absent | 149 | PIT membership overlaps 2015–2025; no `data/raw/{PIT ticker}.csv` |
| Of which left in 2015 and never rebalance-encountered | 20 | `rebalance_encountered=false` |
| Rebalance listing-CSV absent | **129** | Engine can see the name after warmup |
| Of 129 with proven vendor coverage under another ticker | **16** | `G_data_under_other_ticker` |
| Of 129 still unresolved / unavailable | **113** | `D_unresolved_identity` and `local_listing_csv=false` |

**129 = 113 D + 16 G.**

The 16 G names already have valid local series under a Security Master yahoo
symbol (`ABC→COR`, `ANTM→ELV`, `BF.B→BF-B`, `BHGE→BKR`, `BLL→BALL`,
`BRK.B→BRK-B`, `CTL→LUMN`, `FI→FISV`, `FLT→CPAY`, `HRS→LHX`, `JEC→J`,
`KORS→CPRI`, `RE→EG`, `TMK→GL`, `UTX→RTX`, `WLTW→WTW`). They are listing-CSV
gaps, not price gaps.

The 20 non-rebalance 2015 leavers (`ALTR`, `AVP`, `CFN`, `CMCSK`, `COV`, `DNR`,
`DTV`, `FDO`, `HCBK`, `HSP`, `JOY`, `KRFT`, `LO`, `MWV`, `PETM`, `PLL`, `QEP`,
`SIAL`, `SWY`, `WIN`) are outside the engine’s rebalance population. They still
lack prices if a full-window research corpus is desired, but they are not the
113.

Partial (8), not in the 113: `DOW`, `FOX`, `FOXA`, `HOT`, `IR`, `SCG`, `SNDK`,
`VLTO`. Unusable (2), not in the 113: `HAR`, `PARA`. Recycle listings with a
CSV that is the wrong security: `CCE`, `TEG`, `SE` (Spectra interval).

---

## 3. Missing-data categories

Population: the **113** rebalance-encountered rows in `missing.csv` with
`reason=D_unresolved_identity` and `local_listing_csv=false`.

Primary category is mutually exclusive. Secondary tags are noted in the
solution column. `vendor_symbol_mismatch` is **0** in this 113; those cases
are the 16 G rows.

| Category | Count | Examples | Likely solution |
|----------|-------|----------|-----------------|
| acquired_delisted | 68 | `ATVI`, `CELG`, `ALXN`, `TWTR`, `XLNX`, `WFM`, `FRC`, `SIVB` | Delisted-capable vendor OHLCV keyed by stable ID. Do not alias to acquirer (`ATVI↛MSFT`, `CELG↛BMY`). |
| identity_chain_unresolved | 15 | `CBS`/`VIAB`/`VIAC`, `DISCA`/`DISCK`, `LLL`, `RTN`, `DWDP` | Identity-aware vendor **plus** Security Master. Predecessor/acquirer CSV is not coverage (`WBD.csv` ≠ `DISCA`). |
| still_listed_download_hole | 12 | `AVB`, `EA`, `EQR`, `BK`, `MMC`, `HOLX` | Identity proof, then existing yfinance path. Recycle risk is low, not zero. |
| ticker_change_successor_listed | 10 | `COG→CTRA`, `CDAY→DAY`, `GPS→GAP`, `SYMC→NLOK→GEN` | Security Master listing/yahoo intervals; successor series (some already local: `GEN.csv`, `DOC.csv`, `RVTY.csv`). |
| ticker_recycling_risk | 8 | `SE`-class pattern: `DO`, `CHK`, `CA`, `ADS`, `FL`, `DNB` | Must not fetch the live ticker. Needs historical occupancy + stable ID. |
| vendor_symbol_mismatch | 0 | — | Already handled as the 16 G rows. |
| cannot_recover_without_CRSP_class | 0 as primary | residual overlay | See §7. After a Norgate/Sharadar-class dataset, a minority of combination/new-issuer cases may still be unprovable to CRSP PERMNO standard. |

### 3.1 still_listed_download_hole (12)

PIT ticker still names a going-concern listed equity, or membership ran into
2026 under that ticker. Missing because never downloaded, not because Yahoo
lacks a live series.

| PIT ticker | PIT end | Issuer (evidence) |
|------------|---------|-------------------|
| AVB | open | AvalonBay |
| EA | open | Electronic Arts |
| EQR | open | Equity Residential |
| BK | 2026-05-21 | Bank of New York Mellon (left index 2026; still listed) |
| HOLX | 2026-04-09 | Hologic |
| MMC | 2026-01-14 | Marsh McLennan |
| CTRA | 2026-05-07 | Coterra Energy (current ticker after `COG`) |
| DAY | 2026-02-09 | Dayforce (current ticker after `CDAY`) |
| CMA | 2024-06-24 | Comerica (left index; still listed as of this research) |
| SEE | 2023-12-18 | Sealed Air |
| HBI | 2021-12-20 | Hanesbrands |
| TGNA | 2017-06-02 | TEGNA |

Likely solution: seed identity (CIK + listing interval), then fetch via the
existing historical provider. This is **not** a bulk Yahoo dump of the 113.

### 3.2 ticker_change_successor_listed (10)

Same issuer continues; listing ticker changed. Yahoo often remaps history onto
the current symbol (Block `SQ→XYZ` pattern). Acquirer mapping is not this
category.

| PIT ticker | Successor | Local successor CSV | Notes |
|------------|-----------|---------------------|-------|
| COG | CTRA | no | Cabot Oil & Gas → Coterra |
| CDAY | DAY | no | Ceridian → Dayforce |
| GPS | GAP | no | Gap Inc. ticker change after index removal |
| FBHS | FBIN | no | Fortune Brands Home & Security |
| HCP | PEAK then DOC | `DOC.csv` exists | Do not use `DOC.csv` as HCP until Security Master continuity is seeded |
| PEAK | DOC | `DOC.csv` exists | Healthpeak ticker change |
| SYMC | NLOK then GEN | `GEN.csv` exists | Symantec → NortonLifeLock → Gen Digital |
| NLOK | GEN | `GEN.csv` exists | Intermediate ticker |
| HFC | DINO | no | HollyFrontier → HF Sinclair |
| PKI | RVTY | `RVTY.csv` exists | PerkinElmer → Revvity |

Likely solution: evidence-backed Security Master rows (same CIK / same Class A),
then G-style vendor join. Local `GEN.csv` / `DOC.csv` / `RVTY.csv` must not be
joined on ticker guess.

### 3.3 ticker_recycling_risk (8)

Fetching the PIT string today is the `HAR`/`SE` failure mode.

| PIT ticker | PIT end | Why recycle-unsafe |
|------------|---------|-------------------|
| ADS | 2020-06-22 | Alliance Data later `BFH`; `ADS` is reusable |
| CA | 2018-11-06 | CA Technologies acquired; `CA` is a generic token |
| CHK | 2018-03-19 | Chesapeake bankruptcy; later `CHK` is a different listing |
| DNB | 2017-04-05 | Dun & Bradstreet take-private; later `DNB` IPO is a new listing |
| DO | 2016-10-03 | Diamond Offshore; local-style Yahoo fetch is unsafe |
| FL | 2019-08-09 | Foot Locker; short ticker, occupancy not proven |
| GAS | 2016-07-01 | AGL Resources combination; `GAS` reused |
| XL | 2018-09-12 | XL Group acquired; `XL` occupancy not proven |

Likely solution: vendor with historical ticker occupancy and a non-recycled
security ID. Yahoo ticker fetch is disallowed for these without identity proof.

### 3.4 identity_chain_unresolved (15)

Predecessor, split, or combination where this project already refuses silent
aliasing. Local successor files exist for several and are **not** coverage.

| PIT ticker | Problem | Local file that must not be guessed as this security |
|------------|---------|------------------------------------------------------|
| CBS | ViacomCBS / Paramount chain; `PARA` already identity_mismatch | `PARA.csv` |
| VIAB | Viacom Class B predecessor | `PARA.csv` / `WBD.csv` |
| VIAC | ViacomCBS ticker before Paramount | `PARA.csv` |
| DISCA | Discovery Class A → WBD combination | `WBD.csv` |
| DISCK | Discovery Class C | `WBD.csv` |
| DISH | EchoStar combination | — |
| LLL | L3 Technologies; Harris/`LHX` is a different surviving issuer | `LHX.csv` (Harris, already seeded) |
| RTN | Raytheon Company; UTC/`RTX` is a different surviving issuer | `RTX.csv` (UTC, already seeded) |
| DWDP | DowDuPont; split into DOW / DD / CTVA | `DOW.csv` (partial, different interval) |
| MYL | Mylan → Viatris (`VTRS`) new listed vehicle | `VTRS.csv` |
| PX | Praxair / Linde merger of equals → `LIN` | `LIN.csv` |
| WRK | WestRock / Smurfit combination → `SW` | `SW.csv` |
| WYND | Wyndham split | — |
| ARNC | Alcoa / Arconic / Howmet split | `HWM.csv` |
| XEC | Cimarex combination into Coterra | `CTRA` not local |

Likely solution: vendor assetid/PERMNO/permaticker for **this** listing, plus
Security Master rules already used for TKO (new CIK = new security) and ESRX
(do not alias to acquirer).

### 3.5 acquired_delisted (68)

Independent listing ended by acquisition, take-private, failure, or liquidation.
Need historical OHLCV through the PIT interval. Do not map onto the acquirer.

AABA, ABMD, AGN, ALXN, ANSS, APC, ARG, ATVI, BBBY, BCR, BRCM, BXLT, CELG, CERN,
CPGX, CSRA, CTLT, CTXS, CVC, CXO, DFS, DRE, ENDP, ESV, ETFC, FLIR, FRC, FTR,
GGP, GMCR, HES, IPG, JNPR, JWN, K, KSU, LLTC, LM, LVLT, MJN, MNK, MON, MRO,
MXIM, NBL, NFX, NLSN, PBCT, PCP, PDCO, PXD, RAI, RHT, SIVB, SNI, SPLS, SRCL,
STJ, SWN, TIF, TSS, TWC, TWTR, VAR, WBA, WCG, WFM, XLNX.

Examples:

- `ATVI` Microsoft combination 2023 — need Activision bars, not `MSFT.csv`
- `ESRX` is **not** in the 113; local series already covers the PIT interval
- `FRC` / `SIVB` — listing failure; last bars are the research object
- `ANSS`, `HES`, `JNPR`, `WBA`, `DFS`, `IPG`, `K` — 2024–2025 combinations;
  still require the **target** series through PIT end

Likely solution: Norgate-class delisted tape (or Sharadar SEP / CRSP). Yahoo
is not an acceptable primary for this bucket.

### 3.6 Full 113 assignment

acquired_delisted (68): AABA, ABMD, AGN, ALXN, ANSS, APC, ARG, ATVI, BBBY, BCR,
BRCM, BXLT, CELG, CERN, CPGX, CSRA, CTLT, CTXS, CVC, CXO, DFS, DRE, ENDP, ESV,
ETFC, FLIR, FRC, FTR, GGP, GMCR, HES, IPG, JNPR, JWN, K, KSU, LLTC, LM, LVLT,
MJN, MNK, MON, MRO, MXIM, NBL, NFX, NLSN, PBCT, PCP, PDCO, PXD, RAI, RHT, SIVB,
SNI, SPLS, SRCL, STJ, SWN, TIF, TSS, TWC, TWTR, VAR, WBA, WCG, WFM, XLNX.

identity_chain_unresolved (15): ARNC, CBS, DISCA, DISCK, DISH, DWDP, LLL, MYL,
PX, RTN, VIAB, VIAC, WRK, WYND, XEC.

still_listed_download_hole (12): AVB, BK, CMA, CTRA, DAY, EA, EQR, HBI, HOLX,
MMC, SEE, TGNA.

ticker_change_successor_listed (10): CDAY, COG, FBHS, GPS, HCP, HFC, NLOK, PEAK,
PKI, SYMC.

ticker_recycling_risk (8): ADS, CA, CHK, DNB, DO, FL, GAS, XL.

---

## 4. Requirements

Minimum market-data specification implied by this codebase. Fields are not
added merely because a vendor offers them.

### 4.1 Daily bar fields (required)

| Field | Why |
|-------|-----|
| date / timestamp | Bar identity. Inclusive `[start, end]`. Timezone-aware in CSV import. |
| open, high, low, close | Stored on `MarketBarModel`. Dollar-volume uses **unadjusted** `close * volume`. |
| volume | Liquidity filter. |
| adjusted_close | Momentum uses **adjusted_close only** (`app/strategy/calculations.py`). Missing adj close is an error, not silently substituted. |

Warm-up: typically 2013-07-08 → 2025-12-31 so lookback 252 has sessions.

### 4.2 Identity capabilities (required)

| Capability | Why |
|------------|-----|
| Historical daily OHLCV for US exchanges | PIT S&P 500 members 2015–2025 |
| Adjusted prices with documented methodology | Momentum is a total-return-style ratio if adj includes dividends |
| Delisted securities | 68 of 113 plus HAR/CCE/TEG/Spectra SE |
| Historical ticker changes | G-16 pattern and the 10 ticker-change names |
| Stable security identifier | Recycle (`SE`, `CHK`, `DO`) |
| Historical symbol resolution as-of date | `resolve_security(ticker, as_of)` |
| Survivorship-bias-free prices | Delisted names remain in PIT |
| Securities that disappeared before 2025 | Acquired/merged/failed |
| Distinguish ticker change vs new security | `SQ→XYZ` vs TKO vs `ESRX↛CI` |

### 4.3 Not required for the current strategy

| Field | Verdict |
|-------|---------|
| shares outstanding | Not read by momentum or dollar-volume |
| Corporate-action event table (splits, dividends as rows) | Optional quality audit of `adjusted_close`; not consumed by the engine |
| Intraday / quotes | Out of scope |
| Official S&P membership feed | Universe problem, not this market-data purchase (vendor constituents may later **validate** fja05680) |

**Adjustment spec:** this project’s Yahoo path uses `auto_adjust=False` and
stores Yahoo `Adj Close` (split **and** dividend adjusted). A vendor that only
split-adjusts OHLC is **PARTIAL** unless a dividend-inclusive adjusted close
is also provided.

**Corporate actions:** needed as *identity evidence* (ticker change vs new
issuer vs combination). Not needed as a separate stored table unless used to
rebuild adjusted close.

**SEC:** CIK, ticker-history filings, issuer identity, corporate-event evidence.
Not an OHLCV source.

---

## 5. Provider comparison

Ratings: YES / PARTIAL / NO / UNKNOWN. UNKNOWN is not treated as YES.
Vendor facts checked against public pages on 2026-09-02. No mass download.
No `.env` credentials used.

### 5.1 Comparison matrix

| Provider | Daily OHLCV | Adjusted prices | Delisted | Ticker history | Stable ID | Corporate actions | PIT suitability | API | Cost (public) | Verdict |
|----------|-------------|-----------------|----------|----------------|-----------|-------------------|-----------------|-----|---------------|---------|
| CRSP US Stock | YES | YES | YES | YES | YES (PERMNO/PERMCO) | YES | YES | PARTIAL (WRDS/flat files) | UNKNOWN commercial; academic institutional | Research-grade. Not obtainable for this individual project. |
| Norgate US Platinum | YES | YES | YES | YES | YES (`assetid`) | YES | YES | PARTIAL (local Python, not REST) | USD 630 / 12 months Platinum | **Recommended primary** |
| Sharadar SEP | YES | YES | YES | YES | YES (permaticker) | YES | PARTIAL | YES | UNKNOWN (login-gated) | **Recommended API fallback** |
| Polygon / Massive | YES | PARTIAL (split; dividend not confirmed) | PARTIAL | PARTIAL (experimental ticker-events) | PARTIAL (FIGI/CIK) | YES | PARTIAL | YES | Basic free (2y); Starter USD 29/mo (5y); Developer USD 79/mo (10y); Advanced USD 199/mo (all history) | History too short below Advanced; identity weaker than Norgate/CRSP |
| Tiingo Power | YES | YES (CRSP-style) | PARTIAL | PARTIAL (`permaTicker`) | PARTIAL | YES | PARTIAL | YES | USD 30/mo or USD 300/yr individual | Cheapest professional probe; delisted completeness unproven |
| Alpha Vantage | YES | YES (premium adjusted) | PARTIAL | NO | NO | PARTIAL | NO | YES | Free 25 req/day; premium from USD 49.99/mo | Not a PIT primary |
| Yahoo / yfinance (current) | YES | YES | NO | NO | NO | PARTIAL | NO | PARTIAL (unofficial) | Free unofficial | Convenience for live tickers only |
| Nasdaq / NYSE listed feeds | PARTIAL | UNKNOWN | NO | PARTIAL | PARTIAL | UNKNOWN | NO | PARTIAL | UNKNOWN | Not a historical delisted identity product |
| SEC EDGAR | NO | NO | NO | PARTIAL | PARTIAL (CIK) | PARTIAL | NO | YES | Free | Identity evidence only |
| Official SPDJI | NO as OHLCV | NO | N/A | PARTIAL (membership) | PARTIAL | N/A | PARTIAL (universe) | UNKNOWN | UNKNOWN licensed | Membership, not prices |

### 5.2 CRSP

- Daily US stocks, active and inactive, PERMNO (security) / PERMCO (company).
- Ticker history in names files; corporate actions; delisting returns.
- Survivorship-bias-free when used with PERMNO, not ticker.
- Access: WRDS for subscribing academic institutions; commercial license from
  CRSP / Morningstar Indexes; **no individual self-serve tier**.
- Cost: not publicly listed. Institutional. Academic WRDS is for
  non-commercial research at subscriber universities.
- Legal use here: **not currently licensed**. Do not scrape or share CRSP.
- Verdict: gold standard. Option C for research-grade. Not the operational
  primary.

Sources: [CRSP US Stock Databases](https://www.crsp.org/products/research-products/crsp-us-stock-database/),
WRDS subscriber policy.

### 5.3 Norgate Data

- US major-exchange equities. Platinum: history to 1990, **delisted**, OTC
  formerly listed, **historical index constituents** including S&P 500 `$SPX`
  daily from March 1957.
- Delisted symbols use a last-trade suffix (`ALOG-201806`) so recycled tickers
  do not collide. `assetid` is a static ID through symbol changes, exchange
  moves, and delisting.
- Surviving-entity vs merger-of-equals rules are documented (new `assetid` on
  merger of equals). That matches this project’s TKO vs UTC/RTX distinction
  **if** mapped carefully in Security Master.
- Adjustments configurable (price return vs total return). Needed: a
  dividend-inclusive adjusted close aligned with Yahoo Adj Close.
- Python: `norgatedata` on PyPI. Requires **Norgate Data Updater** running.
- NDU is **Windows-only**. On this Mac: Windows VM (Parallels / UTM / VMware);
  Python must run where NDU runs. Native Mac/Linux is a stated medium-term plan,
  not available on 2026-09-02.
- Licensing: subscription, two personal machines, internal use. Not a hosted
  REST API.
- Cost: Platinum USD 346.50 / 6 months or **USD 630 / 12 months**. Diamond
  (to 1950) USD 787.50 / 12 months. Silver/Gold **exclude delisted** and
  historical constituents — insufficient.
- Survivorship: Platinum+ is designed for it. Norgate does not claim a complete
  1950s delisted tape; 2015–2025 S&P 500 members are inside the extensive
  delisted set (tens of thousands of names).
- Verdict: strongest practical source for this project’s PIT + delisted +
  identity needs.

Sources: [stock market packages](https://norgatedata.com/stockmarketpackages.php),
[data content tables](https://norgatedata.com/data-content-tables.php),
[FAQ / assetid](https://norgatedata.com/data-package-faq.php),
[NDU FAQ Mac](https://norgatedata.com/ndu-faq.php),
[norgatedata PyPI](https://pypi.org/project/norgatedata/).

### 5.4 Polygon / Massive

Rebranded Massive (polygon.io → massive.com) as of 2026.

- US stocks aggregates, reference tickers with `date` as-of, `active=false`
  for inactive, CIK / composite FIGI / share-class FIGI.
- Ticker Events `GET /vX/reference/tickers/{id}/events` is **experimental**
  and, when given a ticker, returns events for the entity **currently**
  represented by that ticker — the Spectra/SE failure mode unless FIGI/CUSIP
  is used.
- Aggregates: `adjusted=true` by default means **split** adjustment. Dividend
  adjustment of close is **not documented as CRSP-style**. Marked PARTIAL.
- History by individual plan (docs, 2026-09-02): Basic 2 years, Starter 5 years,
  Developer 10 years, Advanced all history (records cited from 2003-09-10).
  From 2026-09-02, Developer 10 years does **not** cover 2013-07 warm-up or
  early 2015. **Advanced (~USD 199/month)** is the first plan that covers this
  research window.
- Delisted: inactive tickers exist; coverage of every 2016–2020 S&P dropout
  is **PARTIAL / not proven here** (no sample download).
- Verdict: usable API, weak identity vs recycle, expensive to cover 2013–2025.

Sources: [Massive stocks](https://polygon.io/stocks),
[ticker events](https://massive.com/docs/rest/stocks/corporate-actions/ticker-events),
[aggregates plan history](https://massive.com/docs/rest/stocks/aggregates/custom-bars),
[pricing](https://massive.com/pricing).

### 5.5 Tiingo

- EOD OHLCV plus adjOpen/High/Low/Close, `divCash`, `splitFactor`. Adjustment
  documented as CRSP methodology (splits and dividends).
- Meta endpoint + daily `supported_tickers.zip`. `permaTicker` for delisted or
  recycled symbols (documented on fundamentals; EOD uses the same ticker/
  permaTicker pattern).
- Vendor statement (AmiBroker forum, 2021-06-22, Rishi at Tiingo): delisted
  included **if covered and ticker not yet recycled**; delisted “from approx.
  2015 onward”; permaticker for recycled names. That is **PARTIAL**, dated,
  and not re-verified with a live authenticated catalog in this task
  (authentication required for a coverage audit).
- Power plan: USD 30/month or USD 300/year individual; 100,000 req/day;
  30+ years history for covered symbols. Starter free: 500 unique symbols/month,
  50 req/hour — not a universe fill tool.
- Verdict: best cheap API for currently listed + some delisted. Not a
  substitute for Norgate/CRSP on recycle-heavy S&P history.

Sources: [EOD docs](https://www.tiingo.com/documentation/end-of-day),
[pricing](https://www.tiingo.com/about/pricing),
[Tiingo delisted forum](https://forum.amibroker.com/t/tiingo-and-delisted-stocks/26140).

### 5.6 Alpha Vantage

- `TIME_SERIES_DAILY_ADJUSTED`: OHLCV, adjusted close, dividend, split.
  Full history is a **premium** function (`outputsize=full`).
- `LISTING_STATUS&state=delisted` lists delisted symbols with `delistingDate`.
  A list is not a survivorship-free price tape. Third-party checks have found
  inconsistent delisted **prices**.
- No PERMNO/assetid. Ticker is the key. Recycle handling: **NO**.
- Free: 25 requests/day (2026). Premium from USD 49.99/month (75 req/min).
- Verdict: not suitable as primary historical vendor for this PIT gap.

Sources: [documentation](https://www.alphavantage.co/documentation/),
[premium](https://www.alphavantage.co/premium/).

### 5.7 Nasdaq / NYSE

Exchange market-data products (SIP, official lists, non-professional feeds)
supply current and some historical listed activity. They do not, as a
self-serve research tape for this repo, provide PERMNO-class identity plus
delisted S&P members 2015–2025 plus ticker occupancy. Nasdaq Data Link is a
**distribution** channel (Sharadar and others), not itself the identity model.

Verdict: **NO** as the historical OHLCV+identity source.

### 5.8 SEC

EDGAR CIK, filings, ticker-change 8-Ks, combination closes. Used already for
seeded identities (`SE`, `XYZ`, `TKO`, `ESRX`, …).
`company_tickers.json` is **current-ticker only** and cannot reconstruct 2015
`SE` = Spectra Energy.

Verdict: identity evidence. Not OHLCV.

### 5.9 Sharadar SEP (additional credible source)

- End-of-day prices and actions for 20,000+ active **and delisted** US
  companies from 1998; `SHARADAR/TICKERS`, `ACTIONS`, `SEP`.
- S&P 500 constituents table from 1957 (vendor reconstruction / Sharadar, not
  a claim of official SPDJI licensing in this doc).
- Designed as survivorship-bias-free fundamentals+prices. Permaticker is the
  stable key (Nasdaq Data Link / Sharadar table model).
- API and bulk tables. Mac-native. Fits Option B with Security Master.
- Pricing: QuantRocket and Nasdaq Data Link pages are **login- and
  license-gated** as of 2026-09-02. Cost is **UNKNOWN**. Professional vs
  non-professional license applies. Do not invent a dollar figure.
- Verdict: best Mac-native API-shaped alternative to Norgate if a quote is
  obtained and the license fits personal research.

Sources: [Sharadar](https://sharadar.com/),
[Nasdaq SEP](https://data.nasdaq.com/databases/SEP),
[QuantRocket Sharadar pricing](https://www.quantrocket.com/pricing/data/sharadar/).

### 5.10 Other sources not recommended as primary

- **EOD Historical Data (EODHD)** and similar retail “delisted CSV” vendors:
  not evaluated with a reliability audit here. Do not adopt an obscure scrape
  feed to fill the 113.
- **Bloomberg / FactSet / Refinitiv**: institutional terminals; capable, not
  practical for this repo, cost UNKNOWN/high.
- **OpenFIGI**: current FIGI mapping, not a price tape (already rejected as
  an identity oracle in Security Master audit).

---

## 6. Known-symbol evaluation

Critical tests applied to each provider:

1. Represent a name removed from the S&P 500 in 2018 and delisted in 2020?
2. Distinguish two securities that used the same ticker at different times?
3. Distinguish a ticker change from a new security?
4. Provide a historical security identifier that prevents ticker contamination?

| Test | CRSP | Norgate | Sharadar | Polygon | Tiingo | AV | Yahoo |
|------|------|---------|----------|---------|--------|----|-------|
| 2018 drop / 2020 delist prices | YES | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO |
| Recycled ticker → two IDs | YES | YES | YES | PARTIAL | PARTIAL | NO | NO |
| Ticker change ≠ new issuer | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO | NO |
| Stable ID for Security Master | YES PERMNO | YES assetid | YES permaticker | PARTIAL FIGI | PARTIAL permaTicker | NO | NO |

### 6.1 Known cases

| Case | Problem | Required capability | CRSP | Norgate | Sharadar | Polygon | Tiingo | AV | Yahoo |
|------|---------|---------------------|------|---------|----------|---------|--------|----|-------|
| SE | Ticker recycling (Spectra vs Sea) | Historical occupancy + two IDs | YES | YES | YES | PARTIAL | PARTIAL | NO | NO (local file is Sea) |
| HAR | Vendor series ≠ Harman | Delisted Harman prices by ID | YES | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO (mismatch CSV) |
| PARA | Local CSV ≠ Paramount | Identity-aware PARA / VIAC chain | YES | YES | YES | PARTIAL | PARTIAL | NO | NO (mismatch CSV) |
| CCE | File after listing; not CCEP | Delisted CCE; no acquirer alias | YES | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO |
| TEG | File after listing; not WEC | Delisted Integrys | YES | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO |
| TKO | New issuer; clip WWE bars | New ID from 2023-09-12 | YES | YES | PARTIAL | PARTIAL | PARTIAL | NO | PARTIAL (remap + clip) |
| XYZ | Same Class A ticker change | Continuity under one ID | YES | YES | YES | PARTIAL | YES | PARTIAL | YES (remap) |
| GME | Same ticker, same security | Ordinary listed history | YES | YES | YES | YES | YES | YES | YES |
| ESRX | Delisted; do not alias to CI | Delisted prices through 2018-12-21 | YES | YES | YES | PARTIAL | PARTIAL | PARTIAL | YES (already local) |

Norgate YES on TKO assumes `assetid` follows “new entity on combination”
similar to CIK 0001973266. That must be **verified in a later sample probe**,
not assumed from marketing text. Until probed, treat as YES for capability
class, with a residual risk that vendor surviving-entity rules differ from
this repo’s TKO rule.

---

## 7. 113-name analysis

No prices were downloaded. Estimates use category membership and vendor
capability class.

| Recovery path | Count | Share of 113 | Examples |
|---------------|-------|--------------|----------|
| Identity proof + existing yfinance | 12 | 11% | AVB, EA, EQR, BK, MMC, HOLX |
| Security Master ticker alias + successor series | 10 | 9% | COG/CTRA, SYMC/GEN, PKI/RVTY |
| Delisted vendor tape (acquired/failed) | 68 | 60% | ATVI, CELG, FRC, XLNX |
| Identity-aware vendor + no acquirer guess | 15 | 13% | CBS/VIAC, LLL, RTN, DWDP |
| Recycle-safe historical ID (not live ticker) | 8 | 7% | DO, CHK, CA, ADS |

**Likely recoverable with a Norgate Platinum / Sharadar-class dataset plus
Security Master mapping:** on the order of **90–105 of 113** (about **80–95%**),
conditional on vendor actually having each name. Norgate documents an extensive
delisted US tape; it does not claim completeness.

**Likely recoverable with Yahoo only (identity-first, no delisted vendor):**
the 12 still-listed holes plus a subset of ticker-changes whose successor CSV
already exists and can be evidence-mapped (`GEN`, `DOC`, `RVTY`) — about
**15–22 names**. That does **not** fix ATVI/HAR/SE Spectra.

**Cannot be guaranteed without a CRSP-class identifier model** (PERMNO or
equivalent discipline), even after Norgate/Sharadar:

- Combination chains this repo refuses to alias (`LLL` vs `LHX`, `RTN` vs `RTX`,
  `CBS/VIAB/VIAC/PARA`, `DISCA/DISCK/WBD`, `MYL/VTRS`, `PX/LIN`)
- New-issuer vs surviving-issuer disagreements (TKO-class)
- Any name the chosen vendor simply does not carry

That residual is estimated **10–25 names**, not the whole 113. CRSP is not
required to *start* filling delisted S&P members; it is required to *claim*
academic-grade PERMNO identity for every combination.

Overlay (not a second count): HAR, PARA, CCE, TEG, Spectra-SE are outside the
113 but need the same delisted/identity vendor. The 8 partials (`DOW`, `FOX`,
…) need identity + possibly predecessor history, not a different vendor class.

---

## 8. Provider limitations

| Provider | Limitation that blocks using it as the sole PIT tape |
|----------|------------------------------------------------------|
| Yahoo | Recycles tickers; drops or remaps delisted; no stable ID |
| Alpha Vantage | Ticker-keyed; inconsistent delisted prices; rate limits |
| Tiingo | Delisted-from-2015-if-not-recycled is incomplete vs 2015–2018 S&P dropouts; permaTicker coverage unproven here |
| Polygon | Plan history: need Advanced for 2013–2025; split-only adj; ticker-events experimental; current-ticker bias |
| Norgate | Windows NDU; not REST; `assetid` is vendor-specific; index constituents are Norgate’s, not official SPDJI; adjustment mode must be set to match Adj Close |
| Sharadar | Price UNKNOWN until quote; license professional/non-professional; not CRSP PERMNO |
| CRSP | Not licensed here; academic WRDS is not a personal API |
| SEC | No prices |
| Nasdaq/NYSE | No delisted identity tape for this workflow |
| fja05680 membership | Unofficial; orthogonal to prices but still a research-readiness blocker |

**One provider is not enough for this architecture.**

- **Option A** (one vendor solves identity + delisted + OHLCV + actions +
  historical ticker): **NO** for operational use. Even CRSP would still need
  a mapping layer onto PIT listing tickers from fja05680.
- **Option B** (Security Master + market-data vendor + SEC/other identity):
  **YES. This is the target.**
- **Option C** (CRSP-class dataset for true research-grade coverage): **YES
  as an upgrade**, not as the next purchase. Individual access is the blocker.

---

## 9. Cost / practicality

All figures public on 2026-09-02. UNKNOWN stays UNKNOWN.

### Minimum viable

**What:** Identity-first Yahoo fill of the 12 still-listed holes; optional
Tiingo Power (USD 300/year) metadata + sample prices for a handful of delisted
tickers; Security Master seeds for ticker-changes that already have successor
CSVs (`GEN`, `DOC`, `RVTY`).

**Cost:** ~USD 0–300/year.

**Cannot guarantee:** delisted coverage, recycle safety for `HAR`/`DO`/`CHK`,
survivorship-bias-free research, the other ~90 names of the 113.

### Recommended

**What:** Norgate US **Platinum** (USD 630 / 12 months) as primary historical
tape; keep yfinance for convenience on currently listed names; keep SEC for
identity evidence; keep internal `security_id`. Windows VM operational cost
on this Mac. If Norgate is impractical, obtain a **Sharadar SEP quote** before
buying Polygon Advanced.

**Cost:** USD 630/year Norgate, or Sharadar UNKNOWN, plus engineering time.
Polygon Advanced at USD 199/month (~USD 2,388/year) is worse value for EOD PIT.

**Cannot guarantee:** official S&P membership; PERMNO-level combination
identity; 100% of the 113; Norgate completeness of every 2015 delist.

### Research-grade

**What:** CRSP daily US stock (PERMNO) via WRDS or commercial CRSP license;
preferably official SPDJI historical constituents; Security Master maps
PERMNO ↔ `security_id` ↔ PIT ticker.

**Cost:** UNKNOWN / institutional. Not a self-serve checkout.

**Cannot guarantee:** nothing in this list is “complete research” until
membership is official and accounting residuals (ESRX-style) are designed.
CRSP still does not make `--universe current` valid.

---

## 10. Recommended source strategy

**Strategy A + C hybrid (primary A, research-grade C later).**

| Role | Choice |
|------|--------|
| Primary historical vendor | **Norgate US Platinum** |
| Fallback (Mac-native API) | **Sharadar SEP** after a written quote; else Tiingo Power for a limited probe |
| Research-grade | **CRSP** if/when licensed |
| Convenience / current listed | **yfinance** (existing `HISTORICAL` provider) |
| Identity evidence | **SEC EDGAR** + existing Security Master |
| Not primary | Alpha Vantage, Polygon below Advanced, Nasdaq/NYSE SIP, Yahoo for delisted |

**Why Norgate first:** delisted tape, `assetid`, ticker occupancy, historical
S&P 500 constituents (later validation of fja05680), total-return adjustment
control, cost far below Polygon Advanced, Python access, designed for
survivorship-aware backtests.

**Fallback why Sharadar not Polygon:** Sharadar is EOD + delisted +
permaticker + S&P constituents from 1998/1957. Polygon’s cheap plans miss
2013–2015; identity is FIGI/current-ticker biased; adjustment is split-first.

**Why not CRSP now:** cannot legally obtain it as an individual checkout.

Do **not** acquire a full vendor universe in this phase. Do **not** replace
Security Master with vendor IDs.

---

## 11. Target architecture

Do not implement in this task.

```
                    ┌───────────────┐
                    │ PIT Universe  │
                    │ listing ticker│
                    │ + interval    │
                    └───────┬───────┘
                            ↓
                    Security Master
                    security_id / seed_key
                            ↓
              vendor_symbol + vendor_security_id
                            ↓
                  Market Data Provider
                            ↓
                    Historical Bars
                    (OHLCV + adj close)
                            ↓
                     Quality Gate
                  identity + price-quality
                            ↓
                       Backtest
                   PostgreSQL market_bars
```

Where identifiers live:

| Identifier | Lives | Role |
|------------|-------|------|
| `ticker` | PIT membership; `security_tickers` scheme `listing` | Time-varying exchange symbol. Never canonical. |
| `security_id` / `seed_key` | `securities` | Canonical identity. Unchanged. |
| `vendor_symbol` | `security_tickers` scheme per vendor (today `yahoo`; later `norgate` / `sharadar`) | File name or API symbol, including Norgate delisted suffix. |
| `vendor_security_id` | `security_identifiers` (`id_type` = `NORGATE_ASSETID` / `PERMNO` / `FIGI` / `TIINGO_PERMATICKER`) | Join key to the vendor tape. Attribute, not a replacement for `security_id`. |
| CIK | `security_identifiers` | Issuer evidence from SEC. Not share-class unique. |

Backtest continues to read PostgreSQL. `market_bars.stock_id` may remain a
ticker row in a first vendor adapter; the quality gate must still resolve
`security_id` before bars are treated as identity-valid. A later migration can
attach `security_id` on bars. That migration is **out of scope**.

---

## 12. Acquisition plan

1. **Do not mass-download** the 113 from Yahoo.
2. **Do not subscribe in this task.** This document is the decision record.
3. Next engineering task: **vendor coverage proof on a frozen sample** after
   a subscription decision (see §17 in the wrap-up below). Metadata-only or
   single-symbol history for known cases `SE` (Spectra), `HAR`, `ESRX`,
   `ATVI`, `XYZ`, plus ~10 names from each 113 category.
4. If Norgate: install NDU in a Windows VM; `pip install norgatedata`; map
   `assetid` → `security_id`; export daily bars into the existing CSV /
   `market_bars` shape (`symbol,timestamp,open,high,low,close,adjusted_close,volume`).
5. If Sharadar: obtain quote and license class; map permaticker → `security_id`.
6. Keep yfinance for still-listed holes **after** identity seed.
7. Re-run `scripts/audit_market_data_coverage.py` offline after any import.
8. Do not start Strategy Research. Do not change momentum, portfolio,
   slippage, commission, or accounting.

---

## 13. Remaining risks

Evidence-backed only:

1. Unofficial fja05680 S&P 500 membership ([HISTORICAL_UNIVERSE_AUDIT.md](HISTORICAL_UNIVERSE_AUDIT.md)).
2. 716/754 window names still UNRESOLVED in Security Master (seed is
   exceptions-only). A vendor ID does not auto-resolve them.
3. 113 rebalance names still have no proven local series.
4. HAR and PARA remain unusable identity_mismatch; CCE/TEG/Spectra-SE remain
   wrong or empty Yahoo series.
5. Partial coverage names (`DOW`, `FOX`, `FOXA`, `HOT`, `IR`, `SCG`, `SNDK`,
   `VLTO`) are recycling/new-listing risks, not simple holes.
6. ESRX-style unvalued residuals after a true listing end are accounting, not
   missing bars.
7. Norgate Windows VM is an operational risk on darwin.
8. Sharadar cost and license class are UNKNOWN until quoted.
9. Vendor surviving-entity rules may disagree with TKO / LLL / RTN policy.
10. `--universe current` remains survivorship-biased if used.
11. Proven vendor CSVs are not automatically in `market_bars` until imported.
12. No CRSP license.

---

## 14. Research-readiness impact

**research_ready = false**

This investigation chooses a vendor class. It does **not** fill prices, does
**not** resolve the 716 UNRESOLVED identities, and does **not** certify
membership. Tests passing and a written recommendation do not make a
historical S&P 500 research backtest.

| Phase | Status |
|-------|--------|
| PHASE 0 — Foundation | COMPLETE |
| PHASE 1 — Backtest Infrastructure | COMPLETE |
| PHASE 2 — Historical Universe | PARTIAL |
| PHASE 3 — Integrity / Accounting | PARTIAL |
| PHASE 4 — Historical Data Quality | **IN PROGRESS** |
| PHASE 5 — Strategy Research | **NOT STARTED** |

**RESEARCH READY: NO**

---

## Final recommendation (ten answers)

1. **Primary market-data source:** Norgate US Platinum (historical tape), with
   Security Master remaining canonical identity.
2. **Why:** Delisted coverage, `assetid`, ticker occupancy, historical S&P 500
   constituents, adjustable total-return prices, Python access, ~USD 630/year
   versus Polygon Advanced ~USD 199/month, and a documented survivorship
   design. Yahoo cannot safely fill the 113.
3. **Sufficient for survivorship-bias-free research?** **No, not by itself.**
   Prices plus delisted names remove one bias source. Unofficial membership,
   UNRESOLVED identities, and accounting residuals remain. Norgate Platinum is
   the first vendor class that can make the **price** side survivorship-aware.
4. **Delisted securities:** Yes, at Platinum/Diamond. Silver/Gold do not.
5. **Ticker changes / recycling:** Yes via `assetid` and delisted suffixes,
   mapped through Security Master intervals (same pattern as `SE` / `XYZ`).
6. **Stable identifier to connect to Security Master:** Norgate `assetid` stored
   on `security_identifiers`. Fallback Sharadar `permaticker`. Research-grade
   CRSP `PERMNO`. Never Yahoo symbol. CIK remains issuer evidence, not
   share-class identity.
7. **Expected recoverable share of the 113:** about **80–95%** with a
   Norgate/Sharadar-class tape plus Security Master mapping; about **11–20%**
   with identity-first Yahoo only.
8. **Impossible without CRSP-class:** guaranteed PERMNO-level treatment of
   every combination/new-issuer edge (`LLL` vs Harris, `RTN` vs UTC, Paramount
   chain, DowDuPont split, TKO-class disagreements), and any name a
   commercial EOD vendor simply omits. Academic comparability to CRSP papers.
9. **Acquire data now or investigate further first?** **Do not acquire the
   full tape yet.** Perform a **sample coverage proof** on known cases and
   category exemplars immediately after choosing Norgate vs Sharadar. Still
   no universe-wide download.
10. **Exact next engineering task:** Vendor coverage proof on a frozen sample
    (`SE` Spectra, `HAR`, `ESRX`, `ATVI`, `XYZ`, plus ~10 names from each of
    the five 113 categories). Metadata / single-symbol history only. Map
    vendor ID → `security_id` design. No Strategy Research. No Backtest Engine
    changes except a throwaway adapter if required for the probe.

**Fallback recommendation:** Sharadar SEP (quote first). Secondary fallback:
Tiingo Power for a cheap incomplete probe — not for claiming PIT completeness.

**Research-grade option:** CRSP daily + PERMNO when a lawful license exists.

---

## Vendor coverage probe (2026-09-02) — additive evidence

This section does **not** replace §§1–14 or the ten answers above. It records
the frozen-sample proof that those answers called for.

Full write-up: [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md).
Machine-readable: [`audit/vendor_coverage_probe.csv`](../../audit/vendor_coverage_probe.csv),
[`audit/vendor_coverage_probe.json`](../../audit/vendor_coverage_probe.json).

**Live result:** Norgate is **NOT TESTABLE IN CURRENT ENVIRONMENT**. Host is
macOS arm64. No Windows VM (Parallels / UTM / VMware / VirtualBox). No NDU.
`norgatedata` is not installed. No Norgate / Tiingo / Sharadar credentials.
Installing Platinum would download the full local US tape; that mass download
was refused.

**Frozen sample** (37 rows): ATVI, CELG, XLNX, FRC, SIVB; CBS, VIAB, VIAC,
LLL, RTN, DWDP; AVB, EA, EQR, BK, MMC, HOLX; COG, CTRA, SYMC, GEN, PKI, RVTY;
DO, CHK, CA, ADS; SE 2015 Spectra, SE 2018 Sea, HAR Harman, HAR current,
ESRX, SQ, XYZ, WWE, TKO, GME. Every row: `identity_status=NOT_TESTABLE`,
`coverage_status=NOT_TESTABLE`, no `vendor_security_id`.

**Documented field correction (does not erase §5.3):** Norgate `assetid`,
delisted `-YYYYMM` symbols, `price_timeseries`, and `TOTALRETURN` adjustment
remain documented YES. **Prior symbols are documented NO.** Official FAQ:
only the current symbol is stored; history is prepended onto it. “Ticker
occupancy” in §§5.3 and 10 therefore means delisted suffix + `assetid`, not
a historical-ticker API. Security Master listing intervals remain mandatory
to map PIT ticker + date onto a vendor symbol. Option B is unchanged.

**Known cases (SE, HAR, ESRX, ATVI, CELG, XLNX, FRC, SIVB, TKO, XYZ, GME):**
not live-evaluated. Do not copy the YES cells in §6.1 as frozen-sample proof.
TKO surviving-entity residual remains open.

**Fallback:** Tiingo Power and Sharadar SEP were not queried (no keys). Yahoo
was not used for this sample.

**Verdict:** **PROMISING — REQUIRES FULL TRIAL**. Not PROVEN SUITABLE. Not
REJECTED. No `app/data/providers/norgate.py`. No production data change.

**Next engineering task (replaces item 10 above as the current next step):**
obtain a lawful Norgate Platinum trial in a Windows VM where NDU already has
data, **or** obtain a Tiingo key / Sharadar quote for a limited authenticated
probe of this same frozen sample. Still no universe-wide download. Still no
Phase 5.

**RESEARCH READY: NO**

---

## Norgate full-trial protocol (2026-09-02) — additive

This paragraph does **not** replace the probe results above or §§1–14.

A written live-trial protocol now exists:
[NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md).

It reuses the same 37-row frozen sample, records official environment
requirements (Windows 10/11 VM, NDU, US Platinum, local DB ~2 GB download /
9.1 GB on disk), and defines identity / coverage / price / special-case
pass-fail rules **before** any live query. `scripts/probe_norgate_trial.py`
and `app/data/providers/norgate.py` were **not** created. Live fields remain
NOT_TESTABLE. Verdict remains **PROMISING — REQUIRES FULL TRIAL**.

The trial still cannot run on this Mac. PHASE 4 remains IN PROGRESS.
PHASE 5 remains NOT STARTED. RESEARCH READY remains NO.

---

## Addendum (2026-09-03) — 2-year vendor-validation GO

This addendum does **not** rewrite §§1–14 or the ten answers. Platinum remains
the recommended **full-history** class.

The current official vendor-validation window is **2024-09-03 → 2025-12-31**
(observed Trial `first_quoted` ∩ this project's PIT endpoint). Protocol:
[NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md).

A 2-year Vendor Validation Ready pass is **Project Construction GO** only.
It is not Full Historical Research Ready and does not start Phase 5.

