# Historical Market Data Coverage Audit

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

This document records Phase 4 coverage and identity work after Security Master
was introduced. It does **not** claim the pipeline is research-ready.

Prior evidence is preserved:

- [SECURITY_MASTER_AUDIT.md](SECURITY_MASTER_AUDIT.md)
- [PRICE_QUALITY_VALIDATION.md](PRICE_QUALITY_VALIDATION.md)
- [HISTORICAL_UNIVERSE_AUDIT.md](HISTORICAL_UNIVERSE_AUDIT.md)

Machine-readable output from `python scripts/audit_market_data_coverage.py`
(offline; no membership download):

- [`audit/market_data_coverage/coverage.csv`](../../audit/market_data_coverage/coverage.csv)
- [`audit/market_data_coverage/coverage.json`](../../audit/market_data_coverage/coverage.json)
- [`audit/market_data_coverage/missing.csv`](../../audit/market_data_coverage/missing.csv)

## 1. Dataset scope

| Item | Value |
|------|--------|
| Research window | 2015-01-01 → 2025-12-31 inclusive |
| Local prices | `data/raw/{SYMBOL}.csv` (OHLCV; `sp500_historical.csv` is not a ticker) |
| Vendor | Yahoo via yfinance when a file is fetched; otherwise local cache only |
| Canonical processed store | PostgreSQL `market_bars` (not rewritten in this step) |
| Warm-up corpus start | typically 2013-07-08 for files imported with Momentum lookback 252 |

Coverage is **not** “CSV exists”. It is the overlap of identity-valid local
prices with each name’s PIT membership interval clipped to the research window.

New local files acquired in this step (minimum necessary, after identity mapping):

| Vendor symbol | Source | Range | First close | Retrieval |
|---------------|--------|-------|-------------|-----------|
| BRK-B | yfinance | 2013-07-08 → 2025-12-31 | 115.01 | 2026-09-02 |
| BF-B | yfinance | 2013-07-08 → 2025-12-31 | 27.60 | 2026-09-02 |

No bulk download of delisted PIT tickers was performed.

## 2. PIT universe scope

Source: public reconstruction [fja05680/sp500](https://github.com/fja05680/sp500),
cached at `data/raw/sp500_historical.csv`. **Not** official S&P Dow Jones Indices.
Official membership accuracy remains **UNCERTAIN**.

| Scope | PIT unique | Listing CSV present | Listing CSV absent |
|-------|------------|---------------------|--------------------|
| Membership overlapping 2015-01-01 → 2025-12-31 | 754 | 605 | **149** |
| Calendar-month PIT from 2016-01-01 (engine rebalance-encountered after warmup) | 724 | 595 | **129** |

The price-quality run’s “129 missing” is the rebalance-encountered subset.
Twenty names left the index in 2015 and never appear after warmup:
`ALTR`, `AVP`, `CFN`, `CMCSK`, `COV`, `DNR`, `DTV`, `FDO`, `HCBK`, `HSP`,
`JOY`, `KRFT`, `LO`, `MWV`, `PETM`, `PLL`, `QEP`, `SIAL`, `SWY`, `WIN`.

PIT membership was **not** deleted for missing or unusable prices.

## 3. Security Master scope

Package: `app/security_master/`. Seed:
[`data/security_master/known_identities.json`](../../data/security_master/known_identities.json)
(`source_version` `2026-09-02-coverage`).

Canonical identity remains internal `seed_key` / `security_id`. Ticker is
time-varying. Unmapped ticker+date is **UNRESOLVED**, not a guessed id.

This step added evidence-backed rows only (same-issuer CIK + ticker/name-change
filing, or surviving-issuer CIK after a combination). Acquirer aliases were
not seeded (`ATVI`↛`MSFT`, `ESRX`↛`CI`, `CELG`↛`BMY`, `CCE`↛`CCEP`).

`stocks`, `market_bars`, and `sp500_constituent_memberships` were not rewritten.
A listing→yahoo fetch helper joins proven vendor files under the PIT ticker at
load time. `market_bars.stock_id` stays a ticker row.

## 4. Coverage methodology

Four independent states:

1. PIT membership exists
2. Security identity resolved (or UNRESOLVED)
3. Market data exists (listing CSV and/or catalog vendor CSV)
4. Market data is valid (identity + price-quality)

```
expected = membership [start, end) ∩ research window
vendor_symbol = Security Master yahoo ticker, else the PIT ticker
valid prices = local window ∩ vendor validity ∩ expected
coverage_ratio = coverage_days / expected_days
```

Ticker equality alone does not grant identity continuity. Yahoo remapped
predecessor history is used only when the catalog records `continuity=true`
for that vendor interval (Block SQ→XYZ pattern).

CLI: `python scripts/audit_market_data_coverage.py` (offline).

## 5. Coverage categories

Membership audit classes `a`–`f` in `app/universe/audit.py` are unchanged.
Missing-data reasons are a separate taxonomy in `app/data/pit_coverage.py`:

| Code | Meaning |
|------|---------|
| A_unavailable | Delisted/acquired; no usable vendor series for the PIT interval |
| B_ticker_change | Listing ticker changed; successor series not present locally |
| C_ticker_recycled | Same string, different security, or local file starts after listing end |
| D_unresolved_identity | No Security Master row; no guessed mapping |
| E_vendor_symbol_differs | Share-class punctuation / vendor ticker differs (no local vendor file) |
| F_delisted | Listing ended; local series covers the PIT interval |
| G_data_under_other_ticker | Proven vendor/successor CSV exists under a different symbol |
| H_identity_validation_failed | File present but identity/price-quality fails |
| I_insufficient_evidence | Residual when evidence is incomplete |

Window 2015–2025 (754 PIT names):

| Reason | Count |
|--------|-------|
| D_unresolved_identity | 716 (includes covered-but-unproven ticker-row names) |
| G_data_under_other_ticker | 16 |
| C_ticker_recycled | 3 (SE, CCE, TEG) |
| H_identity_validation_failed | 2 (HAR, PARA) |
| F_delisted | 1 (ESRX) |
| Covered resolved, no problem code | remaining seeded names (GME, XYZ, TKO, …) |

Listing-CSV-absent (149): 133 `D`, 16 `G`.
Rebalance-encountered listing-CSV-absent (129): 113 `D`, 16 `G`.

## 6. Missing-security table

Full enumeration: [`missing.csv`](../../audit/market_data_coverage/missing.csv)
(149 rows; `rebalance_encountered=true` is the 129).

**G — listing CSV absent, valid vendor coverage (16):**

| PIT ticker | Vendor CSV | Security |
|------------|------------|----------|
| ABC | COR | cencora |
| ANTM | ELV | elevance-health |
| BF.B | BF-B | brown-forman-class-b |
| BHGE | BKR | baker-hughes |
| BLL | BALL | ball-corporation |
| BRK.B | BRK-B | berkshire-hathaway-class-b |
| CTL | LUMN | lumen-technologies |
| FI | FISV | fiserv |
| FLT | CPAY | corpay |
| HRS | LHX | l3harris |
| JEC | J | jacobs-solutions |
| KORS | CPRI | capri-holdings |
| RE | EG | everest-group |
| TMK | GL | globe-life |
| UTX | RTX | rtx-corporation |
| WLTW | WTW | wtw-plc |

**D — listing CSV absent, identity UNRESOLVED (133 window / 113 rebalance).**
Includes currently listed holes (`AVB`, `EA`, `EQR`, `BK`, `MMC`, `HOLX`, …)
and acquired/delisted names (`AABA`, `ABMD`, `AGN`, `ALXN`, `ATVI`, …).
These were **not** bulk-downloaded (Yahoo recycle risk; HAR/CCE/TEG/PARA).

## 7. Identity-resolution results

| Ticker | Historical period | Security | Market-data identity | Status | Evidence |
|--------|-------------------|----------|----------------------|--------|----------|
| ANTM / ELV | ANTM to 2022-06-28; ELV after | elevance-health | ELV.csv, continuity | RESOLVED | CIK 0001156039; Anthem→Elevance ticker change |
| ABC / COR | ABC to 2023-08-30; COR after | cencora | COR.csv, continuity | RESOLVED | CIK 0001140859; AmerisourceBergen→Cencora |
| BLL / BALL | BLL to 2022-05-10 | ball-corporation | BALL.csv, continuity | RESOLVED | CIK 0000009389 |
| BHGE / BKR | BHGE to 2019-10-18 | baker-hughes | BKR.csv, continuity | RESOLVED | CIK 0001701605 |
| WLTW / WTW | WLTW to 2022-01-10 | wtw-plc | WTW.csv, continuity | RESOLVED | CIK 0001140536 |
| UTX / RTX | UTX to 2020-04-03 | rtx-corporation | RTX.csv, continuity | RESOLVED | Surviving issuer CIK 0000101829 (not a TKO-style new CIK). RTN is not this security |
| HRS / LHX | HRS to 2019-06-01 | l3harris | LHX.csv, continuity | RESOLVED | Surviving issuer CIK 0000202058. L3 standalone not seeded |
| FLT / CPAY | FLT to 2024-03-25 | corpay | CPAY.csv, continuity | RESOLVED | CIK 0001175454 |
| CTL / LUMN | CTL to 2020-09-18 | lumen-technologies | LUMN.csv, continuity | RESOLVED | CIK 0000018926 |
| KORS / CPRI | KORS to 2018-09-19 | capri-holdings | CPRI.csv, continuity | RESOLVED | CIK 0001530721 |
| RE / EG | RE to 2023-07-10 | everest-group | EG.csv, continuity | RESOLVED | CIK 0001095073 |
| TMK / GL | TMK to 2019-08-08 | globe-life | GL.csv, continuity | RESOLVED | CIK 0000320335 |
| JEC / J | JEC to 2019-12-10 | jacobs-solutions | J.csv, continuity | RESOLVED | CIK 0000052988 |
| FISV / FI | FISV to 2023-06-07; FI after | fiserv | FISV.csv, continuity | RESOLVED | CIK 0000798354; local cache stamped FISV |
| BRK.B | 2010-02-16 → open | berkshire-hathaway-class-b | BRK-B.csv | RESOLVED | CIK 0001067983; Yahoo hyphen form |
| BF.B | 1996-01-02 → open | brown-forman-class-b | BF-B.csv | RESOLVED | CIK 0000014693; Yahoo hyphen form |
| SE 2015 | Spectra membership | spectra-energy | none (local SE.csv is Sea) | RESOLVED listing; vendor UNRESOLVED in 2015 | CIK 0001373835; recycling |
| SE 2018 | Sea Limited | sea-limited | SE.csv from 2017-10-20 | RESOLVED | CIK 0001703399 |
| SQ / XYZ | SQ to 2025-01-21; XYZ after | block-inc-class-a | XYZ.csv, continuity | RESOLVED | unchanged from prior audit |
| TKO | from 2023-09-12 | tko-group-holdings | TKO.csv clipped | RESOLVED | New issuer; no WWE guess |
| HAR | to 2017-03-13 | harman-international | local HAR.csv mismatch | listing RESOLVED; vendor UNRESOLVED | CIK 0000801296 |
| PARA | 2022-02-17 → 2025-08-08 | paramount-global | local PARA.csv mismatch | listing RESOLVED; vendor UNRESOLVED | CIK 0000813828; first close ~101500 not proven Paramount |
| CCE | to 2016-05-31 | coca-cola-enterprises | local CCE.csv after listing | listing RESOLVED; vendor UNRESOLVED | Not mapped to CCEP |
| TEG | to 2015-06-30 | integrys-energy | local TEG.csv after listing | listing RESOLVED; vendor UNRESOLVED | Not mapped to WEC |
| GME | 2013–2025 window | gamestop | GME.csv | RESOLVED | unchanged |
| ESRX | to 2018-12-21 | express-scripts | ESRX.csv ends 2018-12-21 | RESOLVED / F_delisted | CIK 0001532063; not aliased to CI |
| Most other PIT names | membership interval | — | ticker-row if CSV exists | UNRESOLVED | insufficient evidence |

## 8. Suspicious-symbol results

| Symbol | PIT | Local series | Conclusion |
|--------|-----|--------------|------------|
| HAR | Harman `[2006-02-01, 2017-03-13)` | 2013-07-08→2022-03-02, first close ~18614 | **H** identity_mismatch. No fill. No blacklist. Vendor instrument UNRESOLVED |
| PARA | Paramount `[2022-02-17, 2025-08-08)` | 2021-02-12→2025-12-31, first close ~101500 | **H** identity_mismatch. Extreme-first-close is supporting, not the identity proof. `PARA.csv` is not used as VIAC/CBS successor |
| CCE | Coca-Cola Enterprises to 2016-05-31 | 2019-02-27→2020-04-29, first close ~1112 | **C** file starts after listing ended. Not CCEP. Heuristic would still flag extreme close if loaded as a candidate |
| TEG | Integrys to 2015-06-30 | 2015-12-22→2022-03-02, first close ~8207 | **C** file starts after listing ended. Not a 2016+ rebalance member after warmup |
| SE | Spectra to 2017-02-27 | Sea Limited from 2017-10-20 | Two `security_id`s. Spectra membership has coverage_ratio 0 |
| GME | GameStop | first close ~10.66 | RESOLVED / usable |
| XYZ | Block Class A from 2025-07-23 | IPO series stamped XYZ | Same Class A; Yahoo continuity |
| TKO | from 2025-03-24 | CSV includes pre-2023 WWE bars | Pre-2023-09-12 bars clipped; not attributed to TKO |
| ESRX | to 2018-12-21 | 2013-07-08→2018-12-21, first close ~63.27 | Genuine listing end (Cigna combination). Coverage complete for the PIT interval. Unvalued residual after 2018-12-21 is accounting, not missing ESRX bars |

`extreme_first_close >= 1000` still fires only on PARA, HAR, TEG, CCE in the local corpus (NVR first close ~917.66). The heuristic is kept as a defensive rule for UNRESOLVED series. It was not retuned. Identity validation is primary.

## 9. Unresolved identities

716 of 754 window PIT names are UNRESOLVED at the start of their expected interval.

That includes:

- Covered ticker-row names with no seed (identity-unproven, still tradeable on the existing path)
- 113 rebalance-encountered names with no listing CSV and no proven vendor alias
- Partial-coverage unresolved names: DOW, FOX, FOXA, HOT, IR, SCG, SNDK, VLTO (Yahoo windows do not cover the full PIT interval; recycling/new-listing not guessed)

WWE is not seeded. CBS / VIAB / VIAC are not chained to PARA.

## 10. Data-source limitations

1. fja05680 is unofficial.
2. Yahoo does not reliably serve delisted US history; fetching the PIT ticker often returns a recycled instrument (HAR, CCE, TEG, PARA).
3. `company_tickers.json` is current-ticker only and cannot reconstruct historical ticker occupancy.
4. CRSP PERMNO / licensed corporate-action tape is not available.
5. Share-class PIT punctuation (`BRK.B`) is not rewritten at universe import; vendor mapping is the Security Master yahoo scheme.
6. Proven vendor CSVs in `data/raw/` are not automatically in PostgreSQL `market_bars` until imported.

A new source (CRSP-class delisted tape) would be required to cover most of the 113 unresolved missing names. It was **not** acquired.

## 11. Remaining blockers

1. Unofficial S&P 500 membership reconstruction.
2. Most identities still UNRESOLVED (seed is exceptions-only).
3. 113 rebalance-encountered PIT names still have no local listing CSV and no proven vendor alias (acquired/delisted and some still-listed download holes such as `AVB`, `EA`, `BK`).
4. Partial unresolved coverage (DOW/FOX/IR/SNDK/…).
5. HAR and PARA remain unusable (identity_mismatch), not blacklisted.
6. ESRX-style unvalued residuals after a true listing end (accounting incomplete by design).
7. `--universe current` remains survivorship-biased if used.
8. Vendor series with incomplete identity evidence beyond the seeded cases.

## 12. Research-readiness verdict

**research_ready = false**

**NOT READY.**

Tests passing and 16 proven vendor joins do not make a full historical S&P 500
research backtest. PIT membership, identity, and market-data validity are still
incomplete versus the true point-in-time universe.

**PHASE 4 — Historical Data Quality** continues.

**PHASE 5 — Strategy Research was NOT started.**
