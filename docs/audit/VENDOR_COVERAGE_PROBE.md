# Vendor Coverage Probe — Frozen Sample

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

This document records a Phase 4 proof-of-capability experiment against the
recommended historical vendor. It does **not** claim the pipeline is
research-ready. No mass download was performed. Production PostgreSQL
`market_bars` was not modified. Security Master seeds were not changed.
Local `data/raw` CSVs were not replaced. Strategy Research was not started.
No commit is required for this probe.

Machine-readable output:

- [`audit/vendor_coverage_probe.csv`](../../audit/vendor_coverage_probe.csv)
- [`audit/vendor_coverage_probe.json`](../../audit/vendor_coverage_probe.json)

Generator (does not write production data):

- [`scripts/probe_vendor_coverage.py`](../../scripts/probe_vendor_coverage.py)

Prior research (not erased by this probe):

- [HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md](HISTORICAL_MARKET_DATA_SOURCE_RESEARCH.md)

Next step (protocol only; trial not executed):

- [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md) (rewritten 2026-09-03, 14-section spec; live verdict still **NOT TESTABLE**; schema: [`audit/norgate_trial/`](../../audit/norgate_trial/))
- Current vendor-validation window (2026-09-03 decision): **2024-09-03 → 2025-12-31**. Executable protocol: [NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md). This probe's 2013-07-08 coverage comparison below is **not rewritten**.

Probe date: **2026-09-02**.

---

## 1. Environment

Host: macOS Darwin 25.4.0, arm64 (Apple silicon). Project Python 3.14.6 in
`.venv`. `DATA_PROVIDER=CSV`.

| Check | Result |
|-------|--------|
| Norgate Data Updater (NDU) | Not installed. NDU is Windows-only. |
| Windows VM (Parallels / UTM / VMware Fusion / VirtualBox) | **Not present** |
| `norgatedata` Python package | **Not installed** (`ModuleNotFoundError`) |
| NDU running | No |
| Norgate / Tiingo / Sharadar credentials | **None** in process env or `.env` |
| Full local NDU database | Not present. Installing it would download the subscribed US tape. **Refused.** |

Access questions:

1. Can Norgate be installed/accessed? **NO** on this Mac without a Windows VM.
2. Is a Windows VM available? **NO**.
3. Is the Norgate Python API usable? **NO**.
4. Is authentication/subscription required? **YES**.
5. Can individual-symbol history be queried? **DOCUMENTED YES**, not testable here.
6. Is constituent/security metadata available? **DOCUMENTED YES** at Platinum, not testable here.
7. Is stable `assetid` exposed? **DOCUMENTED YES**, not live-proven.
8. Is ticker history exposed? **DOCUMENTED NO** (official FAQ: prior symbols are not provided).
9. Are delisted securities accessible? **DOCUMENTED YES** at Platinum (`US Equities Delisted`, `-YYYYMM` suffix), not live-proven. First-time access requires the full local database.
10. Can history be exported into this project’s bar shape? **DOCUMENTED YES** (Python DataFrame → `MarketBar`), not live-proven.

**Can Norgate actually be tested?** **NO. NOT TESTABLE IN CURRENT ENVIRONMENT.**

Stop conditions that fired before any live query:

- Norgate requires an unavailable Windows environment.
- Authentication / NDU is unavailable.
- First-time access requires downloading the full subscribed tape (mass download; out of scope).
- Historical ticker occupancy is not a vendor API (current symbol or delisted suffix only).
- Licensing is a paid subscription; none is configured.

No Windows VM was created. No subscription was purchased. `norgatedata` was
not added to `requirements.txt`. No Yahoo fetch of the frozen sample was
performed.

---

## 2. Provider tested

**Intended primary:** Norgate US Platinum.

**Actually queried:** none. Live `norgatedata` calls were not attempted
because the client is not importable and NDU is not running.

**Documentation used (not live prices):**

- https://pypi.org/project/norgatedata/
- https://norgatedata.com/data-package-faq.php
- https://norgatedata.com/ndu-faq.php
- https://norgatedata.com/stockmarketpackages.php

**Fallback live probes:** Tiingo Power and Sharadar SEP were **not** executed.
No API keys were present. Yahoo was not used (HAR / SE recycle policy).

---

## 3. Sample definition

Frozen sample, 37 rows (33 requested tickers plus extra occupancy / predecessor
rows). PIT intervals are from
[`audit/market_data_coverage/coverage.csv`](../../audit/market_data_coverage/coverage.csv)
and seeded identities from
[`data/security_master/known_identities.json`](../../data/security_master/known_identities.json).

| Category | Tickers | Purpose |
|----------|---------|---------|
| A acquired/delisted | ATVI, CELG, XLNX, FRC, SIVB | Own historical security; do not alias to MSFT / BMY / AMD / successor |
| B identity chain | CBS, VIAB, VIAC, LLL, RTN, DWDP | Predecessor/successor; `WBD ≠ DISCA`; do not infer from successor ticker |
| C still-listed holes | AVB, EA, EQR, BK, MMC, HOLX | Required series + stable ID |
| D ticker-change | COG, CTRA, SYMC, GEN, PKI, RVTY | Same vendor ID across COG→CTRA, SYMC→GEN, PKI→RVTY where it is the same security |
| E recycle risk | DO, CHK, CA, ADS | Historical occupancy ≠ currently listed namesake |
| Mandatory known cases | SE (2015 Spectra + 2018 Sea), HAR (Harman + current namesake), ESRX, SQ/XYZ, WWE/TKO, GME | Project-documented behavior |

Required research window for coverage comparison: **2013-07-08 → 2025-12-31**.
A security that did not exist throughout that window is compared against its
own valid interval, not the full window.

---

## 4. Results

Every sample row is **NOT_TESTABLE** for identity and coverage. Vendor
`assetid`, vendor symbol, and first/last dates are empty because no live
lookup ran.

Vendor-class field matrix (official docs; **not** per-symbol proof):

| Field | Documented | Live on sample |
|-------|------------|----------------|
| `vendor_security_id` / `assetid` | YES | UNKNOWN |
| ticker (current symbol) | YES | UNKNOWN |
| historical ticker / prior symbols | **NO** | NO |
| date | YES | UNKNOWN |
| open / high / low / close / volume | YES | UNKNOWN |
| adjusted close (`TOTALRETURN`) | YES | UNKNOWN |
| unadjusted close | YES | UNKNOWN |
| exchange | YES | UNKNOWN |
| security name | YES | UNKNOWN |
| issuer (separate from name) | UNKNOWN | UNKNOWN |
| delisting date (`last_quoted_date`) | YES | UNKNOWN |
| corporate actions (splits, dividends, adjustment modes) | YES | UNKNOWN |

`ticker_history=NO` on every CSV row is a **vendor-level documented fact**,
not a failed live lookup. Norgate FAQ: “Do you provide prior symbols used by
a security? No, only the current symbol is provided.” History is prepended
onto the current symbol. Delisted names use a last-trade `-YYYYMM` suffix.

See the CSV for per-row notes (expected identity, must-not-alias, security-valid
range).

---

## 5. Identity findings

Invariant required: ticker + date → at most one security; the same ticker in
different periods may be different securities.

**Not live-proven.** Documented Norgate identity model:

- Stable key: integer `assetid` (survives ticker change, exchange move, delisting).
- Current lookup key: current symbol, or delisted `SYMBOL-YYYYMM`.
- Occupancy of a recycled ticker is **not** queryable as “SE as of 2015”.
  Mapping PIT ticker + date → vendor symbol still requires this project’s
  Security Master (or an equivalent occupancy table). That is Option B from
  the source research, not a Norgate-only solution.

Correction to earlier research wording (“ticker occupancy” as a Norgate
strength): occupancy is the **delisted suffix + `assetid`**, not a historical
ticker timeseries API. The original source-research sections are retained;
this probe narrows the claim.

Identity chain for a future live trial:

```
historical ticker + as-of date
        → Security Master (listing interval)
        → vendor symbol (current or SYMBOL-YYYYMM)
        → assetid
        → validity [first_quoted_date, last_quoted_date]
        → bars
```

No sample `assetid` was observed. No SE two-ID proof. No HAR Harman proof.
No TKO vs WWE proof. No SQ/XYZ same-`assetid` proof.

---

## 6. Delisted findings

| Sample | Delisted class (live) |
|--------|------------------------|
| ATVI, CELG, XLNX, FRC, SIVB | unknown — historical data availability unproven |
| ESRX | unknown — identity available in Security Master; Norgate prices unproven |
| HAR (Harman) | unknown — identity available in Security Master; vendor prices unproven |
| SE (Spectra) | unknown — identity available; local prices are the wrong security |
| CBS, VIAB, VIAC, LLL, RTN, DWDP | unknown |
| DO, CHK, CA, ADS | unknown — recycle-safe delisted series unproven |

Documented Platinum capability: `US Equities Delisted` database and
`-YYYYMM` suffixes. Documented merger rule: surviving entity keeps `assetid`;
the other is delisted; merger-of-equals creates a new `assetid`. That class
is **promising** for ATVI-style acquirees, but this probe did not see ATVI
bars. It also did not prove the vendor will not prepend acquirer history.

Classification required by the task, applied honestly:

- historical data available: **0** sample names (not tested)
- historical data unavailable: **not demonstrated**
- identity available but prices unavailable: **Norgate identity not live**; project Security Master already has SE / HAR / ESRX / XYZ / TKO / GME
- prices available but identity unresolved: **not demonstrated**

---

## 7. Coverage findings

No vendor first/last dates were obtained.

Comparison rule (unchanged): required range vs security-valid range vs
vendor-data range. Do not fail a name that did not exist for the full
2013-07-08 → 2025-12-31 window (example: HOLX security-valid from 2016-03-30;
TKO from 2023-09-12; XYZ Class A from 2015-11-19 listed, PIT from 2025-07-23).

Coverage status for every row: **NOT_TESTABLE**.

Still-listed holes (AVB, EA, EQR, BK, MMC, HOLX) remain unfilled. They were
not downloaded from Yahoo in this probe.

---

## 8. Adjusted-price findings

Documented: `StockPriceAdjustmentType.TOTALRETURN` (default) adjusts for
capital reconstructions and dividends; `NONE` / `CAPITAL` / `CAPITALSPECIAL`
are also documented. Price timeseries includes Close plus Unadjusted Close
and Dividend columns when applicable.

That is sufficient **as a documented source** for this project’s
`adjusted_close` field (momentum uses adjusted close; calculation logic was
not changed).

**Not live-proven** that TOTALRETURN Close matches Yahoo Adj Close, or that
every sample name carries both splits and dividends. No adjustment-mode
experiment was run.

---

## 9. Failures

This probe did **not** fail Norgate on SE recycling, HAR identity, or acquirer
aliasing, because those tests never ran. The failures are **access** failures:

1. No Windows VM.
2. No NDU / `norgatedata`.
3. No subscription credentials.
4. Full-tape install refused (mass-download stop).
5. No Tiingo or Sharadar fallback credentials.
6. Documented gap: no prior-symbol API, so a live trial still cannot answer
   “what was ticker SE in 2015?” without Security Master or a delisted-suffix
   lookup.

Do not treat documentation YES cells from the earlier source research as
frozen-sample proof.

---

## 10. Limitations

- Norgate is a local full-database product, not a per-symbol REST API.
- Python must run inside the Windows VM where NDU runs.
- Silver/Gold packages exclude delisted history (already recorded; Platinum
  remains the relevant SKU, unsubscribed here).
- Surviving-entity rules may disagree with this repo’s TKO / LLL / RTN policy.
  That residual was already noted; this probe could not confirm or reject it.
- Official S&P membership remains unofficial (fja05680). Orthogonal to vendor
  prices.
- 716/754 window names remain UNRESOLVED in Security Master. A vendor ID does
  not auto-resolve them.
- This probe stored no sample bars under `data/raw` and inserted nothing into
  PostgreSQL.

---

## 11. Recommendation

**Norgate verdict: PROMISING — REQUIRES FULL TRIAL**

Not **PROVEN SUITABLE** (frozen sample was not queried).
Not **INSUFFICIENT** (no live miss of identity or delisted prices).
Not **REJECTED** (no live failure of SE two-IDs, acquirer aliasing, or
current-ticker-only history).

Keep Norgate US Platinum as the **recommended primary class**, with the
narrowing that ticker occupancy is suffix + `assetid` + Security Master, not
a vendor historical-ticker API.

Do **not** implement `app/data/providers/norgate.py` until a trial actually
returns per-symbol `assetid` and bounded history.

Smallest future adapter (design only):

```
Current:  PIT ticker → Security Master → yahoo symbol → market_bars
Potential: PIT ticker → Security Master → NORGATE_ASSETID → vendor bars
           → identity validation → market_bars
```

Store `assetid` on `security_identifiers` (`id_type=NORGATE_ASSETID`). Vendor
symbol may be a delisted suffix. `MarketDataProvider.get_history` still
returns `MarketBar`. Identity clipping stays in `identity_quality`.
`market_bars.stock_id` unchanged.

Next cheapest **executable** probe: Tiingo Power, only after an API key exists.
Sharadar SEP only after a written quote and credential. Do not create
accounts in this task. Do not Yahoo-fill HAR / SE / delisted names.

Live-trial procedure (not executed): [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md).

**RESEARCH READY: NO** (this 2026-09-02 probe; 2013–2025 coverage unproven)

PHASE 4 — Historical Data Quality: **IN PROGRESS**
PHASE 5 — Strategy Research: **NOT STARTED**

Current vendor-validation window (2026-09-03 decision): **2024-09-03 → 2025-12-31**.
See [NORGATE_PLATINUM_TRIAL.md](NORGATE_PLATINUM_TRIAL.md). This probe file and
`audit/vendor_coverage_probe.*` are not rewritten.
