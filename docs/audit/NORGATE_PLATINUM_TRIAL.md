# Norgate 2-Year Vendor-Validation Protocol

**STATUS: PHASE 4 DATA QUALITY TRIAL**

**NORGATE_STATUS: NOT PROVEN — 2-YEAR VENDOR VALIDATION NOT EXECUTED**

**VENDOR_VALIDATION_READY: NO**

**PROJECT_CONSTRUCTION_GO: NO**

**FULL_HISTORICAL_RESEARCH_READY: NO**

**RESEARCH_READY: NO** (full 2013–2025 historical research; not the 2-year GO)

**PHASE_5: NOT STARTED**

Data-integrity work only. This is **not** strategy research. Do not use
return, CAGR, Sharpe, or drawdown as a Norgate result. Do not run the 12-1
backtest as part of this trial.

Official current scope: determine whether Norgate provides sufficiently
reliable, survivorship-aware market data and security identity handling for
the **2-year Trial overlap with this project's PIT endpoint**. A pass is the
GO gate for continuing research-infrastructure construction. It is **not**
full historical research validated.

The scripts exist. Live 2-year artifacts have **not** been written under
[`audit/norgate_platinum_trial/`](../../audit/norgate_platinum_trial/).

Protocol date: **2026-09-03** (2-year window decision).

Prior evidence (not erased, not overwritten):

- [NORGATE_TRIAL_PROTOCOL.md](NORGATE_TRIAL_PROTOCOL.md)
- [VENDOR_COVERAGE_PROBE.md](VENDOR_COVERAGE_PROBE.md)
- Live Trial artifacts: [`audit/norgate_trial/`](../../audit/norgate_trial/)
- Frozen baseline: [`audit/vendor_coverage_probe.json`](../../audit/vendor_coverage_probe.json)
- Frozen sample: [`scripts/probe_vendor_coverage.py`](../../scripts/probe_vendor_coverage.py) (`FROZEN_SAMPLE`)

Do **not** modify the existing probe. Do **not** overwrite Trial artifacts.

---

## 1. Why this 2-year window

Live Trial (2026-09-03, Windows 11 ARM64): NDU + `norgatedata` worked.
`US Equities` and `US Equities Delisted` were listed. All 23 frozen
`SYMBOL-YYYYMM` lookups were `NOT_FOUND`. Six current names resolved
(`GEN`, `RVTY`, `SE`/Sea, `XYZ`, `TKO`, `GME`) with
`first_quoted_date=2024-09-03`. Under the old 2013–2025 coverage rule those
rows stayed `NOT_TESTABLE`.

Norgate Trial is a ~2-year tape. Observed start on live controls is
**2024-09-03**. This project's official PIT / evaluation endpoint remains
**2025-12-31**. The usable overlap is the official vendor-validation window.

Norgate markets a 2-year Trial SKU; the overlap with this PIT endpoint is
~16 calendar months. This is **not** 24 months of strategy research.

**US Stocks Platinum** (history to 1990, populated Delisted) remains the
future **Full Historical Research Ready** class. It is not required for the
current construction GO.

---

## 2. Required package / access (current GO)

| Requirement | Value |
|-------------|--------|
| SKU | **Norgate Trial depth is sufficient** for this GO (first_quoted ≤ 2024-09-03). Platinum is the future full-history class. |
| Client | `norgatedata` inside the Windows environment where NDU runs |
| Databases | `US Equities` required. Historical Delisted populated is **not** required for 2-year P0. |
| Package proof | GME or AVB `first_quoted` **≤ 2024-09-03**; last_quoted empty (open) or **≥ 2025-12-31** |
| APIs | `status`, `databases`, `assetid`, `symbol`, `security_name`, `exchange_name`, `first_quoted_date`, `last_quoted_date`, `price_timeseries` (`TOTALRETURN` and `NONE`, `PaddingType.NONE`) |
| Optional cross-check | `index_constituent_timeseries` for `$SPX` / `S&P 500` |
| Not required | US OTC add-on, futures, forex, fundamentals, production `MarketDataProvider`, pre-2013 history |

Scripts must refuse to persist `database_symbols()` of the full tape.

---

## 3. Architecture

```
fja05680 PIT ticker + as_of
    → listing occupancy (Security Master if seeded, else PIT interval)
    → staged map: occupancy → norgate_symbol (current OR discovered -YYYYMM)
    → assetid
    → staged bars clipped to occupancy ∩ [2024-09-03, 2025-12-31]
    → PIT dict key remains the listing ticker
```

Canonical identity stays `seed_key` / `security_id`. `assetid` is a vendor
attribute stored only in staged mapping files during this trial.

Never: current ticker as historical occupancy. Never: Norgate watchlist as
universe. Never: drop PIT members because prices are missing. Never: write
`market_bars`, seeds, or `data/raw`.

---

## 4. What to acquire

Evaluation window: **2024-09-03 → 2025-12-31**.

Stage (not production) daily OHLCV + TOTALRETURN Close + unadjusted Close +
volume for:

- All PIT listing tickers whose membership overlaps 2024-09-03 → 2025-12-31
  (count derived from cached fja05680; not the 754-name 2015–2025 set).
- Identity overlays that sit outside the 2-year PIT window: Spectra-SE,
  HAR/Harman, Category A/E frozen exemplars, plus Sea Limited.

Clip each series to
`max(2024-09-03, occupancy_start) … min(2025-12-31, occupancy_end or last_quoted)`.
Occupancies with empty intersection are coverage `NOT_TESTABLE`, not FAIL.
Do not require pre-window warmup (HOLX, TKO, XYZ judged on the intersection).

Trial has no bars before 2024-09-03. A 252-session 12-1 lookback cannot emit
signals on day one of this window. That is a documented construction
constraint, not a hidden FAIL, and not Full Historical Research Ready.

Do not export the full US tape into this repository.

---

## 5. Identity, suffixes, recycling

Norgate has **no** prior-symbol API. Delisted key is last-trade
`TICKER-YYYYMM`, which is **not** index-removal date.

Per occupancy:

1. Current ticker only if it still names **this** occupancy (Security Master
   then vs as-of eval end share `seed_key`, or open unresolved PIT occupancy).
2. Frozen suffix from `FROZEN_SAMPLE` (do not silently replace it).
3. Bounded stem discovery (`TICKER-YYYYMM` in Delisted). Do not dump the
   delisted universe into git.
4. Identity = `assetid` + `security_name` + quoted range vs expected issuer.

Ticker changes (same `assetid` **when both sides resolve**): `SQ→XYZ` is
in-window; `COG→CTRA`, `SYMC→GEN`, `PKI→RVTY` use the same rule. Predecessor
miss is PARTIAL, not a silent current-ticker map.

Recycling (two `assetid`s when both resolve): Spectra SE ≠ Sea SE; Harman ≠
current HAR; historical DO/CHK/CA/ADS ≠ current namesakes. Acquirer alias
(ATVI≠MSFT, CELG≠BMY, XLNX≠AMD, ESRX≠CI) is FAIL if the row resolves.
Missing pre-window Delisted suffix is `NOT_TESTABLE`, not PASS.

TKO is a new issuer from 2023-09-12 in this repo. WWE bars labeled as TKO
without a surviving-entity note is FAIL; documented vendor disagreement is
PARTIAL.

---

## 6. Membership join

Canonical universe remains fja05680 → `sp500_constituent_memberships`.
Norgate `$SPX` is a cross-check only. As-of snapshots: **2024-10-01** and
**2025-08-01**. Current-ticker contamination of a historical occupancy is
FAIL. The 2016 Spectra-vs-Sea join is a unit-tested occupancy rule, not an
in-window J1 requirement (Spectra occupancy does not intersect this window).

---

## 7. Staged layout

```
audit/norgate_platinum_trial/
  environment.json
  package_proof.json
  frozen_sample.csv / .json
  mapping/occupancy.csv
  mapping/suffix_discovery.csv
  mapping/conflicts.csv
  bars/totalreturn/{assetid}.csv
  bars/unadjusted/{assetid}.csv
  membership_crosscheck/spx_vs_fja05680.csv
  validation/frozen_matrix.csv
  validation/pit_coverage.csv
  validation/identity_gates.csv
  validation/adjustment_checks.csv
  verdict.json
```

Bar CSV shape: `symbol,timestamp,open,high,low,close,adjusted_close,volume`.
`symbol` is the Norgate vendor symbol. The occupancy map carries the PIT ticker.

---

## 8. Execution sequence

1. Confirm NDU is running with Trial-depth `US Equities` (first_quoted ≤ 2024-09-03).
2. `python scripts/norgate_platinum_package_proof.py` — stop if history starts *after* 2024-09-03.
3. `python scripts/norgate_platinum_frozen_probe.py` — 37-row re-probe.
4. Stop on identity FAIL (recycle collapse or acquirer alias).
5. `python scripts/norgate_platinum_stage.py` — occupancy map + bounded bars.
6. `python scripts/norgate_platinum_validate.py` — matrices + `verdict.json`.
7. Copy `audit/norgate_platinum_trial/` back to this repo if run on the VM.
8. Do not promote. Do not start Phase 5.

---

## 9. Validation matrix

| ID | PASS | FAIL | NOT_TESTABLE |
|----|------|------|----------------|
| P0 | GME/AVB first quoted ≤ 2024-09-03; tape reaches 2025-12-31 or open | History starts after 2024-09-03; listed DB missing | NDU down |
| F1 | No identity FAIL on recycle/acquirer rules | Shared recycle ID; ATVI=MSFT-class | Frozen sample not executed |
| F2 | In-window occupancy ∩ eval window covered | Interior gap / short in-window series | No in-window coverage rows |
| F3 | Same assetid on ticker-change pairs when both resolve | Different IDs without documented split | Predecessor miss only |
| F4 | TKO ≠ WWE **or** documented PARTIAL | WWE bars labeled TKO without note | Both missing |
| U1 | Every window ticker attempted; unresolved counted | Silent current-ticker map onto historical occupancy | Occupancy map missing |
| U2 | Identity-safe in-window series; missing listed as missing | Interior gaps; alias series | Occupancy map missing |
| J1 | 2024-10-01 and 2025-08-01 map via occupancy | Live ticker used for a historical occupancy | |
| M1 | Disagreement file exists; PIT not rewritten | Universe switched to Norgate | `$SPX` API missing |
| A1 | OHLCV + TOTALRETURN + unadjusted + volume | Required column missing | |
| A2 | TOTALRETURN ≠ NONE when actions exist | Identical series despite known split | No action dates (record) |
| I1 | No production writes | Any production write | |
| Q1 | Staged bars pass `validate_historical_parsed_bar` | Negative prices, naive timestamps | |

Lookup success is not PASS. Missing pre-window Delisted history is
`NOT_TESTABLE`, not FAIL. **Missing in-window history inside a valid
occupancy is FAIL.**

---

## 10. Three gates (do not collapse them)

### Vendor Validation Ready

YES only if live 2-year artifacts exist and:

1. `package_proof.json` shows first_quoted ≤ 2024-09-03 and tape to 2025-12-31 (or open).
2. Frozen matrix: zero identity FAIL on recycle/acquirer rules; in-window coverage PASS.
3. Spectra `assetid` ≠ Sea when both resolve; Harman ≠ current HAR when both resolve.
4. SQ/XYZ, COG/CTRA, SYMC/GEN, PKI/RVTY same `assetid` where both resolve.
5. ATVI, CELG, XLNX, FRC, SIVB, ESRX do not alias to acquirers if they resolve.
6. Occupancy map for all 2-year window names; pre-window overlays may be `NOT_TESTABLE`.
7. Join snapshots J1 pass.
8. A1 / A2 / I1 / Q1 pass (A2 may be PARTIAL if no action dates).
9. `verdict.json` is **SUITABLE**, or **PARTIALLY SUITABLE** only for allowed residuals:
   TKO surviving-entity, unofficial fja05680, pre-window Delisted `NOT_TESTABLE`.
10. Production `market_bars`, seeds, CSV provider, and
    `app/data/factory.py` are unchanged.

### Project Construction GO

Equals Vendor Validation Ready. Meaning: continue building backtest/research
infrastructure against Norgate-shaped staged bars for this window. Not
permission to declare 12-1 results, start Phase 5 parameter search, or
promote into production `market_bars`.

### Full Historical Research Ready

**NO** until a later Platinum (or equivalent) trial proves
2013-07-08 → 2025-12-31 delisted/recycle coverage. A 2-year pass does not
set this flag.

Still NO for Vendor Validation Ready if recycle/acquirer FAIL, in-window
coverage FAIL, or current-ticker hits treated as historical occupancies.

---

## 11. Isolation (always)

Forbidden during this trial:

- Mass-export of the US tape into this repo
- Writes to `market_bars`, `stocks`, Security Master seeds, `data/raw`
- Replacing `DATA_PROVIDER=CSV` or adding `NORGATE` to the production factory
- Modifying `scripts/probe_vendor_coverage.py` or Trial/baseline artifacts
- Strategy Research, parameter search, or a 12-1 backtest as a Norgate test
- Replacing PIT with Norgate watchlists
- Guessing PARA/WBD/LHX/RTX/DOW from successors

---

## 12. Scripts

| Script | Role |
|--------|------|
| [`scripts/norgate_platinum_package_proof.py`](../../scripts/norgate_platinum_package_proof.py) | Refuse unless 2-year Trial depth |
| [`scripts/norgate_platinum_frozen_probe.py`](../../scripts/norgate_platinum_frozen_probe.py) | 37-row re-probe → `frozen_sample.*` |
| [`scripts/norgate_platinum_stage.py`](../../scripts/norgate_platinum_stage.py) | Occupancy map + bounded bars |
| [`scripts/norgate_platinum_validate.py`](../../scripts/norgate_platinum_validate.py) | Gates + `verdict.json` |

Helpers: [`app/norgate_trial/`](../../app/norgate_trial/) (not a production
provider). Tests: [`tests/unit/audit/test_norgate_platinum_trial.py`](../../tests/unit/audit/test_norgate_platinum_trial.py).
