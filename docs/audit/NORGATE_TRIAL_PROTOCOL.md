# Norgate Trial Protocol

**STATUS: PHASE 4 DATA QUALITY TRIAL**

**NORGATE_STATUS: NOT PROVEN**

**RESEARCH_READY: NO**

**CURRENT LIVE VERDICT: NOT TESTABLE**

Data-integrity work only. This is **not** strategy research. Do not use
return, CAGR, Sharpe, or drawdown as a Norgate result. Do not run the 12-1
backtest as part of this trial.

This document is the executable protocol for a **future** live Norgate trial
against the existing 37-row frozen sample. It does **not** execute that trial.
It does **not** claim Norgate is suitable.

Protocol date: **2026-09-03**.

Prior evidence (not erased):

- [PRELIMINARY_STRATEGY_BASELINE.md](PRELIMINARY_STRATEGY_BASELINE.md)
- [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md)
- [HISTORICAL_MARKET_DATA_COVERAGE.md](HISTORICAL_MARKET_DATA_COVERAGE.md)
- [HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md](HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md)
- Frozen sample: [`scripts/probe_vendor_coverage.py`](../../scripts/probe_vendor_coverage.py) (`FROZEN_SAMPLE`)
- Isolated trial artifacts: [`audit/norgate_trial/`](../../audit/norgate_trial/)

Evidence classes used below:

| Class | Meaning |
|-------|---------|
| **Verified fact** | Observed on this Mac / in this repo on 2026-09-03 |
| **Documented / inferred** | Official Norgate docs or prior research; not live-proven here |
| **Requires live testing** | Cannot be answered until NDU + Platinum local DB exist |

---

## 1. Objective

Answer only:

> Can Norgate provide historically correct, identity-safe, delisted-aware US
> equity data sufficient to resolve the known historical-data failures in our
> 2015–2025 PIT S&P 500 dataset?

This is a **data quality** investigation.

It is not:

- strategy research or optimization
- another 12-1 backtest
- Norgate production integration
- mass historical download into this repo
- changing PIT membership, Security Master seeds, `DATA_PROVIDER`, PostgreSQL
  `market_bars`, or existing CSVs

Identity correctness is the primary concern. A ticker that exists in Norgate
is **not** proof that it is the correct historical security.

---

## 2. Why Norgate is being evaluated

The 2026-09-03 preliminary 12-1 baseline was **INCONCLUSIVE**. The engine
behaved as designed (PIT membership, next-open fills, costs applied). The
result is not research-grade because **historical market data and identity
resolution are incomplete**. Missing delisted names can bias momentum
**upward**.

Yahoo / local CSVs fail the cases that matter for a survivorship-aware book:

- Delisted and acquired names often have no local file (ATVI, CELG, XLNX, FRC, SIVB).
- Recycled tickers return the wrong issuer (SE Spectra vs Sea; HAR Harman vs later namesake).
- Predecessor/successor chains are not guessed (CBS/VIAB/VIAC, ESRX ≠ CI, WWE ≠ TKO).
- Still-listed download holes remain (AVB, EA, BK, …).

Norgate US Platinum is the previously recommended **vendor class** for
delisted US history and a stable integer `assetid`. That recommendation is
**PROMISING — REQUIRES FULL TRIAL**. It is **not** proven suitable.

---

## 3. Current Phase 4 data problems

**Verified fact** from the preliminary baseline and coverage audit (not
recomputed as a new backtest here):

| Item | Value |
|------|--------|
| Research window | 2015-01-01 → 2025-12-31 (+ warmup from ~2013-07-08) |
| PIT members overlapping window | 754 |
| PIT encountered after warmup | 724 |
| Missing local prices (baseline run) | 115 |
| Unusable series (baseline) | 3: CCE, HAR, PARA |
| Rebalance-visible listing CSV gaps | 129 |
| Proven vendor aliases (other ticker) | 16 |
| Remaining unresolved missing names | 113 |
| Identities UNRESOLVED at interval start | 716 / 754 |
| Baseline verdict | INCONCLUSIVE |
| RESEARCH_READY | NO |

Architecture that Norgate must fit **without** replacing:

```
PIT ticker
    → Security Master (seed_key / security_id)
    → vendor identity (listing / yahoo today)
    → market data
```

Ticker is time-varying. Unknown identity remains **UNRESOLVED**. Do not
redesign Security Master to make Norgate canonical. Do not map by ticker
equality alone.

---

## 4. Frozen 37-row probe

Reuse `FROZEN_SAMPLE` in
[`scripts/probe_vendor_coverage.py`](../../scripts/probe_vendor_coverage.py).
Do **not** invent a second sample. Do **not** silently replace symbols. If a
row cannot be tested, record `NOT_TESTABLE` and why.

Global required window: **2013-07-08 → 2025-12-31**. Coverage is evaluated on
the intersection with each row’s **security-valid** interval, not the full
global window.

| Category | Ticker | Historical period | PIT seed_key | Expected identity | Security-valid | Must not alias |
|----------|--------|-------------------|--------------|-------------------|----------------|----------------|
| A | ATVI | 2015-08-31→2023-10-18 | — | Activision Blizzard | 2015-08-31→2023-10-18 | MSFT |
| A | CELG | 2006-11-06→2019-11-21 | — | Celgene | 2006-11-06→2019-11-21 | BMY |
| A | XLNX | 1999-11-08→2022-02-15 | — | Xilinx | 1999-11-08→2022-02-15 | AMD |
| A | FRC | 2019-01-02→2023-05-04 | — | First Republic Bank | 2019-01-02→2023-05-04 | successor |
| A | SIVB | 2018-03-19→2023-03-15 | — | SVB Financial Group | 2018-03-19→2023-03-15 | successor |
| B | CBS | 1996-01-02→2019-12-05 | — | CBS Corporation | 1996-01-02→2019-12-05 | PARA/WBD |
| B | VIAB | 2006-01-03→2019-12-05 | — | Viacom | 2006-01-03→2019-12-05 | PARA/WBD |
| B | VIAC | 2019-12-05→2022-02-17 | — | ViacomCBS | 2019-12-05→2022-02-17 | PARA |
| B | LLL | 2004-12-01→2019-07-01 | — | L3 Technologies | 2004-12-01→2019-07-01 | LHX |
| B | RTN | 1996-01-02→2020-04-06 | — | Raytheon Company | 1996-01-02→2020-04-06 | RTX |
| B | DWDP | 2017-09-01→2019-06-03 | — | DowDuPont | 2017-09-01→2019-06-03 | DOW/DD/CTVA |
| C | AVB | 2007-01-10→open | — | AvalonBay Communities | 2007-01-10→open | — |
| C | EA | 2002-07-22→open | — | Electronic Arts | 2002-07-22→open | — |
| C | EQR | 2001-12-03→open | — | Equity Residential | 2001-12-03→open | — |
| C | BK | 1996-01-02→2026-05-21 | — | Bank of New York Mellon | 1996-01-02→2026-05-21 | — |
| C | MMC | 1996-01-02→2026-01-14 | — | Marsh & McLennan | 1996-01-02→2026-01-14 | — |
| C | HOLX | 2016-03-30→2026-04-09 | — | Hologic | 2016-03-30→2026-04-09 | — |
| D | COG | 2008-06-23→2021-10-04 | — | Cabot Oil & Gas | 2008-06-23→2021-10-04 | — |
| D | CTRA | 2021-10-04→2026-05-07 | — | Coterra Energy | 2021-10-04→2026-05-07 | — |
| D | SYMC | 2003-03-31→2019-11-05 | — | Symantec | 2003-03-31→2019-11-05 | — |
| D | GEN | 2022-11-08→open | — | Gen Digital | 2022-11-08→open | — |
| D | PKI | 1996-01-02→2023-05-16 | — | PerkinElmer | 1996-01-02→2023-05-16 | — |
| D | RVTY | 2023-05-16→open | — | Revvity | 2023-05-16→open | — |
| E | DO | 2009-02-26→2016-10-03 | — | Diamond Offshore occupancy | 2009-02-26→2016-10-03 | current DO |
| E | CHK | 2006-03-03→2018-03-19 | — | Chesapeake occupancy | 2006-03-03→2018-03-19 | current CHK |
| E | CA | 1996-01-02→2018-11-06 | — | CA Technologies occupancy | 1996-01-02→2018-11-06 | current CA |
| E | ADS | 2013-12-23→2020-06-22 | — | Alliance Data occupancy | 2013-12-23→2020-06-22 | current ADS |
| M | SE | 2015 Spectra | spectra-energy | Spectra Energy Corp | 2007-01-03→2017-02-27 | sea-limited |
| M | SE | 2018 Sea | sea-limited | Sea Limited | 2017-10-20→open | spectra-energy |
| M | HAR | 2006-02-01→2017-03-13 Harman | harman-international | Harman International | 2006-02-01→2017-03-13 | current HAR |
| M | HAR | current namesake | — | Not Harman | unknown | harman-international |
| M | ESRX | 2003-09-26→2018-12-21 | express-scripts | Express Scripts | 2003-09-26→2018-12-21 | CI |
| M | SQ | 2015-11-19→2025-01-21 | block-inc-class-a | Block Class A | 2015-11-19→2025-01-21 | — |
| M | XYZ | 2025-01-21→open | block-inc-class-a | Block Class A | 2025-01-21→open | — |
| M | WWE | predecessor of TKO | — | WWE predecessor | →2023-09-12 | tko-group-holdings |
| M | TKO | 2023-09-12→open | tko-group-holdings | TKO Group Holdings | 2023-09-12→open | WWE |
| M | GME | 2013-07-08→2025-12-31 control | gamestop | GameStop Corp. | PIT 2007-12-14→2016-04-25 | — |

`WBD ≠ DISCA`. Do not infer identity from a successor ticker.

---

## 5. Environment requirements

**Verified fact (2026-09-03, this Mac):** Darwin 25.4.0 arm64; Python 3.14.6;
`norgatedata` not installed; no NDU; no Parallels / UTM / VMware Fusion /
VirtualBox / Windows App; no `prlctl` / `utmctl` / `vmrun` / `VBoxManage`;
`.env` has `DATA_PROVIDER=CSV` and no Norgate keys.

**Documented / inferred** (official Norgate pages; not purchased here):

| Requirement | Documented fact | Source |
|-------------|-----------------|--------|
| OS for NDU | Windows 10/11 or Windows Server 2019/2022/2025 | PyPI, NDU installation |
| Mac native | NDU cannot run natively. Python must run **inside** the Windows VM | PyPI, NDU FAQ |
| Client | `pip install norgatedata` in the VM; NDU must be running | PyPI |
| Subscription | US **Platinum** (or Diamond). Silver/Gold **exclude delisted** — insufficient | stock market packages |
| Local database | Required. Not a REST API. First-time US Platinum: ~2 GB download, ~9.1 GB on disk | NDU installation / package FAQ |
| Per-symbol install | **Not available.** NDU installs the subscribed tape. Trial **queries** stay 37-row | NDU usage |
| Prior symbols API | **Not provided.** History is on the current symbol; delisted names use `-YYYYMM` | package FAQ |
| Stable ID | Integer `assetid` | package FAQ, PyPI |
| PIT index membership | **Must remain** this project’s fja05680 / PostgreSQL PIT layer. Do not switch the universe to a Norgate watchlist in this trial | this protocol |

Do **not** purchase a subscription in this task. Do **not** create credentials.
Do **not** install a VM as part of this protocol write-up.

**Safest future setup:** dedicated Windows 10/11 VM; NDU + Python only inside
the VM; copy `audit/norgate_trial/` artifacts back to this repo. Do not point
NDU at `data/raw` or PostgreSQL.

The vendor-mandated full US tape lives **inside the VM**. That is not a
production `market_bars` ingest.

**The trial cannot be executed from this Mac today.**

---

## 6. Required Norgate capabilities

What the live trial must be able to show (today: **requires live testing**
except where marked documented):

| Capability | Why we need it | Status |
|------------|----------------|--------|
| Know the security by current ticker and/or `TICKER-YYYYMM` | Lookup without guessing acquirers | Requires live testing |
| Integer `assetid` stable across ticker changes | Fit as a *vendor* id next to `seed_key`, not a replacement | Documented YES; not live-proven |
| Security name + exchange | Identity check vs expected issuer | Documented YES; not live-proven |
| First / last quoted date | Coverage vs security-valid ∩ required window | Documented YES; not live-proven |
| Delisted US tape | ATVI-class, FRC/SIVB, historical occupancies | Documented Platinum; Silver/Gold insufficient |
| Distinguish two occupancies of one ticker | SE Spectra ≠ Sea; HAR ≠ later namesake | Requires live testing |
| TOTALRETURN adjusted close | Momentum uses `adjusted_close` | Documented YES; not live-proven |
| Unadjusted close + volume | Dollar volume is `close * volume` | Documented YES; not live-proven |
| Corporate actions (splits/dividends) in TOTALRETURN | Consistent adjusted path | Documented YES; not live-proven |
| Historical ticker occupancy API | Would map PIT ticker as-of | Documented **NO** (current symbol or `-YYYYMM` only) |
| Official S&P PIT constituents | Replace fja05680 | **Out of scope.** PIT stays this repo’s universe |

Norgate **index** constituent timeseries, if present at Platinum, is optional
cross-check only. It must not replace `historical_sp500`.

---

## 7. Test methodology

`scripts/probe_norgate_trial.py` is **not** added in this step.
`norgatedata` is not installed. When a Windows VM + NDU + Platinum local DB
exist, a future isolated script must follow this contract.

Preconditions (refuse to run otherwise):

1. `norgatedata.status()` is true (NDU running).
2. `databases()` includes `US Equities` and `US Equities Delisted`. If the
   delisted DB is missing, stop: not Platinum.
3. Output path is under `audit/norgate_trial/` only.
4. The script does not import `MarketDataService` for writes, does not open a
   production DB session for writes, and does not write `data/raw`.

Per frozen-sample row:

1. Load expected identity from `FROZEN_SAMPLE` (PIT ticker, valid interval,
   expected name, must-not-alias). Do not use ticker-only matching.
2. Lookup **both**:
   - current ticker (e.g. `SE`, `HAR`, `ATVI`)
   - delisted-suffix candidate from security-valid end: `TICKER-YYYYMM`
     (e.g. `SE-201702`, `ATVI-202310`)
3. For each lookup that resolves, record `assetid`, `symbol`, `security_name`,
   `exchange_name`, `first_quoted_date`, `last_quoted_date`.
4. Identity uses `assetid` + `security_name` + quoted range vs expected issuer.
   A successful **current-ticker** lookup is **not** historical identity.
5. Prices: `price_timeseries` twice — `StockPriceAdjustmentType.TOTALRETURN`
   and `NONE` — clipped to eval window, plus a small `limit` for first/last
   evidence. Do not dump `database_symbols`.
6. Confirm columns: Date, Open, High, Low, Close, Volume, and Unadjusted Close
   when present. Padding `PaddingType.NONE`.
7. Write one audit row. Leave
   [`audit/vendor_coverage_probe.csv`](../../audit/vendor_coverage_probe.csv)
   unchanged.

Documented APIs (PyPI; not live-verified here): `assetid`, `symbol`,
`security_name`, `exchange_name`, `first_quoted_date`, `last_quoted_date`,
`status`, `price_timeseries`, `status()`, `databases()`. There is **no**
`historical_ticker()` API.

```
PIT ticker + as-of
        → expected identity (Security Master / this protocol)
        → current symbol lookup  AND  TICKER-YYYYMM lookup
        → assetid(s) + names + quoted dates
        → compare (must not alias)
        → bounded TOTALRETURN + unadjusted bars
        → audit/norgate_trial only
```

---

## 8. Evidence to collect

For every probe row, the live trial must attempt:

1. Does Norgate know the security?
2. Does it have historical data for the required period?
3. What stable security identifier does it provide? (`assetid`)
4. What was the historical ticker? (current symbol vs `-YYYYMM`; prior-symbol
   API is documented unavailable)
5. What is the security/company identity? (`security_name`)
6. Is the security delisted/acquired?
7. First available trading date
8. Last available trading date
9. Does data cover dates required by 12-1 momentum on
   `max(2013-07-08, valid_start)` … `min(2025-12-31, valid_end)`?
10. Does Norgate distinguish predecessor/security identity from later ticker reuse?
11. Can the series be mapped safely to our `security_id` / `seed_key` model
    (comparison only; no seed write)?
12. Is adjusted price history available? (TOTALRETURN Close)
13. Is volume available?
14. Is dollar volume reproducible? (unadjusted close × volume)
15. Are corporate actions handled consistently? (TOTALRETURN vs NONE differ
    when splits/dividends exist; if they do not differ, record that fact)

Row verdicts (per security, after live observation only):

| Verdict | Meaning |
|---------|---------|
| PASS | Identity, coverage, and fields meet acceptance criteria for that row |
| FAIL | Vendor demonstrably wrong (alias, recycle collapse, missing required bars inside valid period) |
| PARTIAL | Some evidence, important gap remains |
| NOT_TESTABLE | Environment or lookup blocked; **all 37 rows today** |

---

## 9. Acceptance criteria

Apply only after **live** observation.

### Identity / recycling

- **SE:** Spectra Energy (2015 occupancy) and Sea Limited (2018 occupancy)
  must be **two** `assetid`s. One continuous series = FAIL. Do not blacklist SE.
- **HAR:** Harman International 2006–2017 ≠ current HAR namesake.
- **DO, CHK, CA, ADS:** historical occupancy `assetid` ≠ currently listed namesake.
- Current ticker must not silently retrieve a previous unrelated company.

### Delisted / acquired (own security, not acquirer)

- ATVI ≠ MSFT, CELG ≠ BMY, XLNX ≠ AMD, ESRX ≠ CI
- FRC / SIVB: own delisted series, not a successor alias

### Identity chains

- CBS, VIAB, VIAC, LLL, RTN, DWDP: predecessor and successor remain **distinct**
  unless live evidence proves one `assetid` **and** the name/dates match a
  single security. Do not guess PARA/WBD/LHX/RTX/DOW.

### Ticker changes (same issuer)

- SQ → XYZ: same Block Class A; want the **same** `assetid`
- COG → CTRA, SYMC → GEN, PKI → RVTY: same `assetid` where it is the same security
- Predecessor lookup failure (current-symbol-only) is a **mapping note**, not
  automatic FAIL, if the successor `assetid` is stable and name/dates match

### TKO / WWE

- This repo: TKO is a **new issuer** from 2023-09-12 (CIK `0001973266`), not a
  WWE rename. Silently serving WWE bars as TKO = not a pass. A documented
  surviving-entity disagreement → PARTIAL / vendor-class PARTIALLY SUITABLE,
  not hidden SUITABLE.

### Coverage / prices

- Required 12-1 history exists on security-valid ∩ global window
- Missing-before listing / missing-after true delist: not a fail
- Gap **inside** valid period: FAIL
- HOLX from 2016-03-30 and TKO from 2023-09-12 do not require 2013 warmup
- OHLCV + TOTALRETURN Close + unadjusted close + volume present
- `GME` control: one stable `assetid` and ordinary daily history

### Production isolation (always)

No PostgreSQL writes, no `market_bars` changes, no PIT edits, no Security
Master seed edits, no `data/raw` overwrite, no `NORGATE` in
[`app/data/factory.py`](../../app/data/factory.py), no strategy edits.

---

## 10. Current testability status

**Verified fact, 2026-09-03:**

| Check | Result |
|-------|--------|
| Host | macOS Darwin 25.4.0 arm64 |
| NDU | Not installed |
| Windows VM apps / CLIs | Not present |
| `norgatedata` in `.venv` | `ModuleNotFoundError` |
| Norgate credentials in `.env` | None |
| Local NDU database | None |
| Production Norgate provider | None (`CSV` / `HISTORICAL` / `IBKR` only) |

Stop conditions (same as the 2026-09-02 vendor probe; still true):

- Norgate requires an unavailable Windows environment.
- Authentication / NDU is unavailable.
- First-time access requires the full subscribed US tape (mass download into
  the VM; out of scope for *this repo*).
- Historical ticker occupancy is not a vendor API.
- No license is configured.

**Can Norgate actually be tested on this Mac?** **NO.**

All 37 probe rows: **NOT_TESTABLE**. Vendor-class status remains
**PROMISING — REQUIRES FULL TRIAL**. Live-field status: **NOT TESTABLE**.

Do not promote documentation YES cells to SUITABLE.

---

## 11. Expected artifacts

Isolated location (not production):

```
audit/norgate_trial/
  environment.json
  schema.csv
  schema.json
```

After a **future live** trial, the same directory should gain observed columns
(not invented now): filled `norgate_identity`, `norgate_asset_id`, dates,
PASS/FAIL/PARTIAL, plus optional `trial.csv` / `trial.json` with
`evidence_type=LIVE`.

Schema columns (this preparation):

`probe_symbol`, `expected_identity`, `norgate_identity`, `norgate_asset_id`,
`historical_ticker`, `first_date`, `last_date`, `required_history_available`,
`delisted_status`, `identity_match`, `ticker_recycling_safe`,
`adjusted_prices_available`, `volume_available`, `corporate_action_handling`,
`verdict`, `notes`

plus local-only comparison fields sourced from
[`audit/market_data_coverage/coverage.csv`](../../audit/market_data_coverage/coverage.csv)
and Security Master notes. Norgate live fields are empty / `NOT_TESTABLE`.

This preparation does **not** create `scripts/probe_norgate_trial.py`,
`app/data/providers/norgate.py`, or schema migrations.

---

## 12. Decision framework

Classify Norgate **only** after live observation, as one of:

| Verdict | When |
|---------|------|
| **SUITABLE** | Live-demonstrated: distinct `assetid`s for recycled tickers (SE, HAR, DO/CHK/CA/ADS); delisted own-securities (ATVI-class, ESRX, FRC/SIVB); ticker changes same id where required (SQ/XYZ, COG/CTRA, …); OHLCV + TOTALRETURN + unadjusted close; coverage on eval windows; TKO handled per this repo **or** explicitly recorded as surviving-entity disagreement |
| **PARTIALLY SUITABLE** | Client runs and returns data, but important identity or coverage cases remain unresolved |
| **NOT SUITABLE** | Vendor aliases acquirees, collapses recycled tickers, or cannot supply required fields |
| **NOT TESTABLE** | Environment or access prevents observation. **This is the current result.** |

Legacy labels in the 2026-09-02 protocol map as: PROVEN SUITABLE → SUITABLE;
INSUFFICIENT → PARTIALLY SUITABLE; REJECTED → NOT SUITABLE.

Do **not** use SUITABLE without live rows.

---

## 13. Limitations

1. fja05680 PIT membership remains unofficial even if Norgate prices pass.
2. Platinum still requires installing the full US tape **in the VM**.
3. Norgate is not an official S&P Dow Jones feed.
4. `assetid` is a vendor attribute to compare, not this repo’s `security_id`.
5. Documented lack of prior-symbol history means PIT ticker as-of still needs
   `-YYYYMM` or Security Master mapping.
6. This protocol does not fill the 113 missing names; it only defines how to
   test whether Norgate *can*.
7. The preliminary baseline CAGR/Sharpe are **not** inputs to this verdict.

---

## 14. Next step

1. Provide a Windows 10/11 VM.
2. Install NDU + US Platinum (user action; not done here). Wait until the
   local delisted database is present.
3. Run a 37-row isolated query per §7; write live rows over
   `audit/norgate_trial/` Norgate columns only.
4. Apply §9 and §12.

Until then:

- PHASE 4 — Historical Data Quality: **IN PROGRESS**
- PHASE 5 — Strategy Research: **NOT STARTED**
- **RESEARCH READY: NO**
- Norgate: **NOT TESTABLE** / **NOT PROVEN**

Do not start parameter optimization. Do not run another strategy backtest as
a Norgate test. Do not integrate Norgate into production.

---

## Addendum (2026-09-03) — 2-year vendor-validation window

The **current official vendor-validation scope** is
**2024-09-03 → 2025-12-31**, the observed Norgate Trial `first_quoted` overlap
with this project's PIT endpoint. That change lives in
[NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md).

This document's 2013-07-08 → 2025-12-31 required window remains the **future
Full Historical Research Ready** gate (Platinum-class delisted tape). It is
not erased. A 2-year Vendor Validation Ready pass is Project Construction GO
only. It is not Full Historical Research Ready and does not start Phase 5.

The frozen 37-row sample and live Trial artifacts under `audit/norgate_trial/`
are unchanged.
