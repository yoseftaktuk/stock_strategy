# Security Master Audit

Data-integrity work only. This is **not** a strategy research result.
Do not use return, CAGR, Sharpe, or drawdown as research.

This document records the Security Master introduced after Phase 4 price-quality
validation. It does **not** claim the pipeline is research-ready.

## Data sources

Used for **known cases only**. No bulk identifier dataset was downloaded.

| Source | Role | Authoritative for |
|--------|------|-------------------|
| SEC / issuer IR | Block SQ→XYZ on 2025-01-21; CUSIP/ISIN unchanged; CIK `0001512673` | Same Class A, ticker change |
| SEC | Spectra Energy merger into Enbridge 2017-02-27; CIK `0001373835` | SE listing end |
| SEC | Sea Limited NYSE:SE IPO 2017-10-20; CIK `0001703399` | Recycled SE listing start |
| SEC | TKO Group Holdings CIK `0001973266` (New Whale Inc.); combination close 2023-09-12 | New issuer, not a WWE ticker rename |
| Local CSVs + PIT cache | Price windows and membership intervals | What the system actually holds |
| Existing Phase 4 audits | HAR/GME/XYZ/TKO/SE observations | Cross-check |

Not used as identity oracles: Yahoo quote pages, OpenFIGI current mapping, CRSP
(PERMNO not licensed). `company_tickers.json` is current-ticker only and cannot
reconstruct 2015 `SE` = Spectra Energy.

Seed file: [`data/security_master/known_identities.json`](../../data/security_master/known_identities.json).

## Identity model

Ticker is time-varying. Security identity is canonical and internal.

```
PIT membership ticker
        → resolve_security(ticker, as_of)     # listing scheme
raw vendor symbol + bar date
        → resolve_market_data_symbol(...)     # yahoo scheme
        → identity_mismatch and/or bar clip
        → existing price-quality
        → BacktestEngine fills
```

Responsibilities stay separate:

- **PIT universe:** was this *name* a constituent on date D?
- **Security Master:** which *security* did ticker X represent on date D?
- **Market data:** do we have bars for that security?

`sp500_constituent_memberships`, `stocks`, and `market_bars` were not rewritten.
`stock_id` remains a `(symbol, exchange)` ticker row.

Types: `Security`, `SecurityTicker`, `SecurityIdentifier`, `Resolution`.
No `SecurityRelationship` table in this phase.

## Identifier strategy

| Identifier | Stability | Historical availability | Coverage | Suitability |
|------------|-----------|-------------------------|----------|-------------|
| Internal `security_id` / `seed_key` | High | Full for seeded rows | Seeded cases only | **Canonical** |
| CIK | Stable for issuer, not share class | EDGAR; current ticker file is not historical | US registrants | Attribute / evidence |
| FIGI | Stable per instrument | OpenFIGI is current mapping | Live/current | Later attribute |
| ISIN / CUSIP | Stable per issue | Licensed | US/global | Not available here |
| Yahoo symbol | Unstable; remaps; recycles | Whatever Yahoo serves today | Wide and often wrong | Never canonical |
| exchange+ticker+interval | Time-bounded | As good as the catalog | Known cases | Ticker model, not identity |

Unmapped tickers resolve as **UNRESOLVED**. They remain tradeable on the existing
ticker-row path. That is identity-unproven, not a guessed `security_id`.

## Ticker interval model

Half-open, matching PIT: `[valid_from, valid_to)`. `valid_to is None` means open.

Two schemes on `security_tickers`:

- `listing` — exchange ticker validity
- `yahoo` — vendor symbol as stored in `data/raw/{SYMBOL}.csv`

Invariant: `(scheme, ticker, date)` resolves to **at most one** security.
The same listing ticker may map to different securities on disjoint intervals
(recycling). Adjacent intervals that share a boundary do not overlap.

`continuity=true` is recorded only when evidence says the vendor remaps history
of the **same** security (Block SQ→XYZ). It is not a guess flag.

## Known cases

| Case | Conclusion | Confidence |
|------|------------|------------|
| **SE** | Recycling. `SE`+2015 → `spectra-energy`. `SE`+2018 → `sea-limited`. Two `security_id`s. Local `SE.csv` is Sea Limited only. Spectra membership has no valid local bars. | High |
| **XYZ** | Ticker change of the same Class A. Listing `SQ [2015-11-19, 2025-01-21)` and `XYZ [2025-01-21, open)` share `block-inc-class-a`. Yahoo stamps the IPO series as `XYZ`; continuity granted. PIT membership remains 2025-07-23 → open. Series is **usable**. | High |
| **TKO** | New issuer, not a ticker rename. Listing/Yahoo `TKO` valid from `2023-09-12`. Pre-2023 `TKO.csv` bars are WWE predecessor history and are **clipped**. PIT TKO 2025-03-24 → open is TKO Group. | High |
| **HAR** | PIT listing is Harman International `[2006-02-01, 2017-03-13)`. Local `HAR.csv` (first close ~18614, continues to 2022-03-02) is **not** Harman. Yahoo vendor mapping omitted → UNRESOLVED. Entire overlapping series is `identity_mismatch`. Membership kept. No ticker blacklist. Exact vendor instrument UNRESOLVED. | High that it is not Harman; vendor identity unresolved |
| **GME** | Listing and Yahoo `GME` resolve to `gamestop` for 2013–2025. Same security. | High |

## Unresolved cases

- Most PIT members: no Security Master row; `resolve_security` returns UNRESOLVED.
- Local Yahoo `HAR` instrument (quote id 906601): not Harman; not identified.
- PARA, CCE, TEG: still heuristic-unusable (`extreme_first_close`); identities UNRESOLVED.
- WWE as a standalone security: not seeded; pre-TKO bars are UNRESOLVED rather than a guessed WWE id.
- Official S&P Dow Jones membership: still UNCERTAIN (fja05680 reconstruction).

## Assumptions

- Internal integer `security_id` plus stable `seed_key` is sufficient while external IDs are incomplete.
- Yahoo continuity is granted only when filings show the same Class A (Block).
- A combination that creates a new CIK (TKO) is a new security even if Yahoo remaps prices.
- UNRESOLVED must not become a silent `security_id`.
- Identity failures must not delete PIT membership.

## Integration boundary

Minimum backtest integration only:

- [`app/data/identity_quality.py`](../../app/data/identity_quality.py) clips vendor-invalid bars and flags `identity_mismatch`.
- [`BacktestEngine`](../../app/backtest/engine.py) unions that with `extreme_first_close`.
- [`run_momentum_backtest`](../../app/backtest/runner.py) loads the static known-identities catalog.
- `market_bars.stock_id` is still a ticker row. No security_id FK on bars.
- No momentum, commission, slippage, timing, or accounting changes.

## Confidence level

Known-case identities: **high**, evidence-backed.
Catalog coverage vs the full PIT universe: **low** (seeded exceptions only).
Research readiness: **NOT READY** (unchanged).

## Limitations

1. Incomplete local prices versus PIT members (129 missing in the Phase 4 window).
2. Security Master covers only seeded names; ticker changes among unmapped names are still invisible.
3. Unofficial fja05680 membership source.
4. Extreme-first-close remains a generic heuristic for unmapped names (PARA/CCE/TEG).
5. Unvalued residuals (ESRX in Phase 4) still make the equity curve incomplete.
6. `--universe current` remains survivorship-biased if used.
7. No CRSP PERMNO / licensed corporate-action tape.

**research_ready = false**

**Strategy Research (project Phase 5) was not started.**
