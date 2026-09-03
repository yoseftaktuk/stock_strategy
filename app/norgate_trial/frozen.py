"""Platinum classification of the frozen 37-row sample."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.norgate_trial.client import LookupResult, parse_iso_date
from app.norgate_trial.constants import (
    ACQUIRER_ALIASES,
    CATEGORY_A_TICKERS,
    EVAL_END,
    EVAL_START,
    STATUS_FAIL,
    STATUS_NOT_TESTABLE,
    STATUS_PARTIAL,
    STATUS_PASS,
    TICKER_CHANGE_PAIRS,
)


class FrozenSampleLike(Protocol):
    sample_category: str
    ticker: str
    historical_period: str
    pit_security: str
    expected_identity: str
    security_valid_from: str
    security_valid_to: str
    must_not_alias: str
    notes_hint: str
    delisted_suffix: str | None


@dataclass
class FrozenRow:
    sample_category: str
    ticker: str
    historical_period: str
    pit_security: str
    expected_identity: str
    security_valid_from: str
    security_valid_to: str
    must_not_alias: str
    delisted_suffix: str
    vendor_security_id: str = ""
    vendor_symbol: str = ""
    security_name: str = ""
    first_date: str = ""
    last_date: str = ""
    identity_source: str = ""
    identity_status: str = STATUS_NOT_TESTABLE
    coverage_status: str = STATUS_NOT_TESTABLE
    verdict: str = STATUS_NOT_TESTABLE
    ticker_change_assetid_match: str = ""
    discovered_suffix: str = ""
    current_asset_id: str = ""
    delisted_asset_id: str = ""
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def as_csv_dict(self) -> dict[str, str]:
        return {
            "sample_category": self.sample_category,
            "ticker": self.ticker,
            "historical_period": self.historical_period,
            "pit_security": self.pit_security,
            "expected_identity": self.expected_identity,
            "must_not_alias": self.must_not_alias,
            "delisted_suffix": self.delisted_suffix,
            "vendor_security_id": self.vendor_security_id,
            "vendor_symbol": self.vendor_symbol,
            "security_name": self.security_name,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "identity_source": self.identity_source,
            "identity_status": self.identity_status,
            "coverage_status": self.coverage_status,
            "verdict": self.verdict,
            "ticker_change_assetid_match": self.ticker_change_assetid_match,
            "discovered_suffix": self.discovered_suffix,
            "current_asset_id": self.current_asset_id,
            "delisted_asset_id": self.delisted_asset_id,
            "notes": self.notes,
        }


def eval_window_for(sample: FrozenSampleLike) -> tuple[date, date]:
    valid_start = parse_iso_date(sample.security_valid_from) or EVAL_START
    valid_end = parse_iso_date(sample.security_valid_to) or EVAL_END
    return max(EVAL_START, valid_start), min(EVAL_END, valid_end)


def coverage_status_for_dates(first: str, last: str, sample: FrozenSampleLike) -> str:
    first_d = parse_iso_date(first)
    last_d = parse_iso_date(last) or EVAL_END
    eval_start, eval_end = eval_window_for(sample)
    if eval_start > eval_end:
        # Occupancy does not intersect the 2-year window. Pre-window delists stay
        # NOT_TESTABLE. A still-listed control whose PIT occupancy ended earlier
        # (GME) PASSes when quotes cover the full vendor-validation window.
        if first_d is None:
            return STATUS_NOT_TESTABLE
        if first_d <= EVAL_START and last_d >= EVAL_END:
            return STATUS_PASS
        return STATUS_NOT_TESTABLE
    if first_d is None:
        return STATUS_NOT_TESTABLE
    if first_d <= eval_start and last_d >= eval_end:
        return STATUS_PASS
    return STATUS_FAIL


def is_alias_identity(vendor_symbol: str, security_name: str, must_not_alias: str) -> bool:
    aliases = _alias_tickers(must_not_alias)
    symbol = (vendor_symbol or "").upper()
    if "-" in symbol:
        symbol = symbol.split("-", 1)[0]
    if symbol in aliases:
        return True
    name = (security_name or "").upper()
    for alias in aliases:
        if alias and alias in name.split():
            return True
    return False


def identity_lookup(
    sample: FrozenSampleLike,
    current: LookupResult,
    suffix: LookupResult,
    discovered: LookupResult | None = None,
) -> tuple[LookupResult | None, str]:
    if sample.delisted_suffix:
        if suffix.found:
            return suffix, "frozen_suffix"
        if discovered is not None and discovered.found:
            return discovered, "discovered_suffix"
        return None, ""
    if current.found:
        return current, "current_ticker"
    return None, ""


def classify_frozen_row(
    sample: FrozenSampleLike,
    current: LookupResult,
    suffix: LookupResult,
    *,
    discovered: LookupResult | None = None,
) -> FrozenRow:
    row = FrozenRow(
        sample_category=sample.sample_category,
        ticker=sample.ticker,
        historical_period=sample.historical_period,
        pit_security=sample.pit_security,
        expected_identity=sample.expected_identity,
        security_valid_from=sample.security_valid_from,
        security_valid_to=sample.security_valid_to,
        must_not_alias=sample.must_not_alias,
        delisted_suffix=sample.delisted_suffix or "",
        current_asset_id=current.assetid if current.found else "",
        delisted_asset_id=suffix.assetid if suffix.found else "",
        discovered_suffix=discovered.symbol if discovered is not None and discovered.found else "",
    )
    parts = [_format_lookup("Current ticker", current)]
    if sample.delisted_suffix:
        parts.append(_format_lookup("Frozen suffix", suffix))
        if discovered is not None:
            parts.append(_format_lookup("Discovered suffix", discovered))
    identity, source = identity_lookup(sample, current, suffix, discovered)
    row.identity_source = source
    alias_hit = False
    if identity is not None:
        row.vendor_security_id = identity.assetid
        row.vendor_symbol = identity.vendor_symbol or identity.symbol
        row.security_name = identity.security_name
        row.first_date = identity.first_date
        row.last_date = identity.last_date
        extra_alias = ACQUIRER_ALIASES.get(sample.ticker, frozenset())
        must_not = sample.must_not_alias
        if extra_alias and not must_not:
            must_not = "/".join(sorted(extra_alias))
        alias_hit = is_alias_identity(row.vendor_symbol, row.security_name, must_not)
        if alias_hit:
            row.identity_status = STATUS_FAIL
        else:
            row.identity_status = STATUS_PASS
        row.coverage_status = coverage_status_for_dates(row.first_date, row.last_date, sample)
    else:
        row.identity_status = STATUS_NOT_TESTABLE
        row.coverage_status = STATUS_NOT_TESTABLE
        if sample.delisted_suffix and current.found:
            parts.append(
                "Current ticker resolved but is not historical identity for this occupancy."
            )
    extra = ""
    if alias_hit:
        extra = " FAIL: resolved identity matches must-not-alias."
    row.verdict = _row_verdict(row.identity_status, row.coverage_status)
    row.notes = (
        f"{' '.join(parts)} Expected identity: {sample.expected_identity}."
        f"{extra} {sample.notes_hint}"
    ).strip()
    return row


def apply_recycle_identity_rules(rows: list[FrozenRow]) -> None:
    se_2015 = next((row for row in rows if row.ticker == "SE" and "2015" in row.historical_period), None)
    se_2018 = next((row for row in rows if row.ticker == "SE" and "2018" in row.historical_period), None)
    if se_2015 is not None and se_2018 is not None:
        spectra_id = se_2015.delisted_asset_id or se_2015.vendor_security_id
        sea_id = se_2018.current_asset_id or se_2018.vendor_security_id
        if spectra_id and sea_id:
            if spectra_id == sea_id:
                se_2015.identity_status = STATUS_FAIL
                se_2015.verdict = STATUS_FAIL
                se_2015.notes = (
                    f"{se_2015.notes} FAIL: Spectra and Sea share assetid {spectra_id} "
                    "(recycle collapse)."
                )
            else:
                se_2015.notes = (
                    f"{se_2015.notes} Recycle-safe: Spectra assetid {spectra_id} != Sea assetid {sea_id}."
                )
                se_2018.notes = (
                    f"{se_2018.notes} Recycle-safe: Sea assetid {sea_id} != Spectra assetid {spectra_id}."
                )
        elif se_2015.delisted_suffix and se_2018.current_asset_id and not spectra_id:
            se_2015.notes = (
                f"{se_2015.notes} Spectra suffix unresolved; recycle two-ID proof incomplete."
            )

    har_harman = next(
        (row for row in rows if row.ticker == "HAR" and "Harman" in row.historical_period),
        None,
    )
    har_current = next(
        (row for row in rows if row.ticker == "HAR" and "current" in row.historical_period),
        None,
    )
    if har_harman is None or har_current is None:
        return
    harman_id = har_harman.delisted_asset_id or har_harman.vendor_security_id
    current_id = har_current.current_asset_id or har_current.vendor_security_id
    if harman_id and current_id:
        if harman_id == current_id:
            har_harman.identity_status = STATUS_FAIL
            har_harman.verdict = STATUS_FAIL
            har_harman.notes = (
                f"{har_harman.notes} FAIL: Harman and current HAR share assetid {harman_id}."
            )
        else:
            har_harman.notes = (
                f"{har_harman.notes} Recycle-safe: Harman assetid {harman_id} "
                f"!= current HAR assetid {current_id}."
            )


def compare_ticker_change_pairs(rows: list[FrozenRow]) -> dict[str, str]:
    by_ticker: dict[str, FrozenRow] = {}
    for row in rows:
        if row.ticker not in {"SE", "HAR"}:
            by_ticker[row.ticker] = row
    matches: dict[str, str] = {}
    for predecessor, successor in TICKER_CHANGE_PAIRS:
        pred = by_ticker.get(predecessor)
        succ = by_ticker.get(successor)
        if pred is None or succ is None:
            matches[f"{predecessor}->{successor}"] = STATUS_NOT_TESTABLE
            continue
        pred_ids = _asset_ids(pred)
        succ_ids = _asset_ids(succ)
        if not succ_ids:
            status = STATUS_NOT_TESTABLE
        elif not pred_ids:
            # Predecessor current-symbol miss is a mapping note if successor exists.
            status = STATUS_PARTIAL
        elif pred_ids & succ_ids:
            status = STATUS_PASS
        else:
            status = STATUS_FAIL
        pred.ticker_change_assetid_match = status
        succ.ticker_change_assetid_match = status
        pred.notes = f"{pred.notes} Ticker-change {predecessor}->{successor} same assetid: {status}."
        succ.notes = f"{succ.notes} Ticker-change {predecessor}->{successor} same assetid: {status}."
        matches[f"{predecessor}->{successor}"] = status
    return matches


def category_a_own_securities(rows: list[FrozenRow]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        if row.ticker not in CATEGORY_A_TICKERS:
            continue
        result[row.ticker] = row.identity_status
    return result


def frozen_suffix_map(samples: list[FrozenSampleLike]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for sample in samples:
        if not sample.delisted_suffix:
            continue
        mapping[sample.ticker] = sample.delisted_suffix
        if sample.security_valid_to:
            mapping[f"{sample.ticker}:{sample.security_valid_to}"] = sample.delisted_suffix
    return mapping


def _row_verdict(identity: str, coverage: str) -> str:
    if identity == STATUS_FAIL or coverage == STATUS_FAIL:
        return STATUS_FAIL
    if identity == STATUS_PASS and coverage == STATUS_PASS:
        return STATUS_PASS
    if identity == STATUS_NOT_TESTABLE or coverage == STATUS_NOT_TESTABLE:
        return STATUS_NOT_TESTABLE
    return STATUS_PARTIAL


def _asset_ids(row: FrozenRow) -> set[str]:
    ids: set[str] = set()
    for value in (row.vendor_security_id, row.current_asset_id, row.delisted_asset_id):
        if value:
            ids.add(value)
    return ids


def _alias_tickers(must_not_alias: str) -> set[str]:
    aliases: set[str] = set()
    if not must_not_alias:
        return aliases
    for part in must_not_alias.replace(",", "/").split("/"):
        token = part.strip()
        if not token or token.lower().startswith("current "):
            continue
        if any(char.islower() for char in token):
            continue
        aliases.add(token.upper())
    return aliases


def _format_lookup(label: str, result: LookupResult) -> str:
    if result.found:
        return (
            f"{label} {result.symbol}: assetid={result.assetid} "
            f"name={result.security_name!r} first={result.first_date} last={result.last_date}"
        )
    error = result.error or "not found"
    return f"{label} {result.symbol}: NOT_FOUND ({error})"


def rows_payload(rows: list[FrozenRow], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "row_count": len(rows),
        "required_window": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
        "rows": [row.as_csv_dict() for row in rows],
    }
    if extra:
        payload.update(extra)
    return payload
