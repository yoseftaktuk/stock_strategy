"""Thin norgatedata wrapper for the Platinum trial.

Queries individual symbols and bounded stem matches. Never persists a full
database_symbols dump.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, cast

from app.norgate_trial.constants import (
    DELISTED_DATABASE_NAME,
    DELISTED_PROBE_SUFFIXES,
    DELISTED_SUFFIX_PATTERN,
    EVAL_END,
    EVAL_START,
    FULL_HISTORY_EVAL_START,
    LISTED_DATABASE_NAME,
    PACKAGE_PROOF_SYMBOLS,
    TRIAL_HISTORY_START,
)

_SUFFIX_RE = re.compile(DELISTED_SUFFIX_PATTERN)


class NorgateClient(Protocol):
    """Subset of norgatedata used by the trial. Tests supply fakes."""

    def assetid(self, symbol: str) -> object: ...

    def security_name(self, symbol: str) -> str | None: ...

    def exchange_name(self, symbol: str) -> str | None: ...

    def symbol(self, assetid: object) -> str | None: ...

    def first_quoted_date(self, symbol: str) -> object: ...

    def last_quoted_date(self, symbol: str) -> object: ...

    def price_timeseries(self, symbol: str, **kwargs: object) -> object: ...


@dataclass
class LookupResult:
    symbol: str
    found: bool = False
    assetid: str = ""
    vendor_symbol: str = ""
    security_name: str = ""
    exchange_name: str = ""
    first_date: str = ""
    last_date: str = ""
    daily_ohlcv: str = "UNKNOWN"
    adjusted_close: str = "UNKNOWN"
    unadjusted_close: str = "UNKNOWN"
    corporate_action_handling: str = "NOT_TESTABLE"
    bar_count_totalreturn: int = 0
    bar_count_none: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "found": self.found,
            "assetid": self.assetid,
            "vendor_symbol": self.vendor_symbol,
            "security_name": self.security_name,
            "exchange_name": self.exchange_name,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "daily_ohlcv": self.daily_ohlcv,
            "adjusted_close": self.adjusted_close,
            "unadjusted_close": self.unadjusted_close,
            "corporate_action_handling": self.corporate_action_handling,
            "bar_count_totalreturn": self.bar_count_totalreturn,
            "bar_count_none": self.bar_count_none,
            "error": self.error,
        }


@dataclass
class PackageProof:
    ndu_running: bool = False
    norgatedata_importable: bool = False
    databases: list[str] = field(default_factory=list)
    delisted_db_present: bool = False
    listed_db_present: bool = False
    delisted_populated: bool = False
    delisted_match_count: int = 0
    history_precedes_trial_cap: bool = False
    trial_capped: bool = False
    proof_symbols: dict[str, dict[str, str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    verdict: str = "NOT_TESTABLE"
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ndu_running": self.ndu_running,
            "norgatedata_importable": self.norgatedata_importable,
            "databases": list(self.databases),
            "delisted_db_present": self.delisted_db_present,
            "listed_db_present": self.listed_db_present,
            "delisted_populated": self.delisted_populated,
            "delisted_match_count": self.delisted_match_count,
            "history_precedes_trial_cap": self.history_precedes_trial_cap,
            "trial_capped": self.trial_capped,
            "proof_symbols": dict(self.proof_symbols),
            "errors": list(self.errors),
            "verdict": self.verdict,
            "notes": self.notes,
            "required_window": {
                "start": EVAL_START.isoformat(),
                "end": EVAL_END.isoformat(),
            },
            "trial_history_start": TRIAL_HISTORY_START.isoformat(),
        }


def iso_date(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text or text.lower() in {"none", "nat", "nan"}:
        return ""
    return text[:10]


def parse_iso_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def empty_lookup(symbol: str, error: str = "") -> LookupResult:
    return LookupResult(symbol=symbol, error=error)


def lookup_symbol(client: NorgateClient, symbol: str, *, fetch_bars: bool = True) -> LookupResult:
    result = empty_lookup(symbol)
    try:
        assetid = client.assetid(symbol)
    except Exception as exc:  # noqa: BLE001 — missing tickers are expected
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    if assetid is None:
        result.error = "assetid returned None"
        return result
    result.found = True
    result.assetid = str(assetid)
    try:
        name = client.security_name(symbol)
        result.security_name = "" if name is None else str(name)
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    try:
        exchange = client.exchange_name(symbol)
        result.exchange_name = "" if exchange is None else str(exchange)
    except Exception:  # noqa: BLE001
        result.exchange_name = ""
    try:
        vendor_symbol = client.symbol(assetid)
        result.vendor_symbol = str(vendor_symbol if vendor_symbol is not None else symbol)
    except Exception:  # noqa: BLE001
        result.vendor_symbol = symbol
    try:
        result.first_date = iso_date(client.first_quoted_date(symbol))
        result.last_date = iso_date(client.last_quoted_date(symbol))
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    if not fetch_bars:
        return result
    totalreturn = price_timeseries(client, symbol, "TOTALRETURN", limit=3)
    none_bars = price_timeseries(client, symbol, "NONE", limit=3)
    result.bar_count_totalreturn = _series_len(totalreturn)
    result.bar_count_none = _series_len(none_bars)
    if result.bar_count_totalreturn:
        result.daily_ohlcv = "YES"
        result.adjusted_close = "YES"
    if result.bar_count_none:
        result.unadjusted_close = "YES"
    differ = _series_differ(totalreturn, none_bars)
    if differ is True:
        result.corporate_action_handling = "PASS"
    elif differ is False:
        result.corporate_action_handling = "PARTIAL"
    return result


def price_timeseries(
    client: NorgateClient,
    symbol: str,
    adjustment: str,
    *,
    start: date = EVAL_START,
    end: date = EVAL_END,
    limit: int | None = None,
) -> object:
    adjustment_type = getattr(client, "StockPriceAdjustmentType", None)
    setting: object = adjustment
    if adjustment_type is not None:
        setting = getattr(adjustment_type, adjustment, adjustment)
    kwargs: dict[str, Any] = {
        "stock_price_adjustment_setting": setting,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timeseriesformat": "pandas-dataframe",
    }
    if limit is not None:
        kwargs["limit"] = limit
    padding_type = getattr(client, "PaddingType", None)
    if padding_type is not None and getattr(padding_type, "NONE", None) is not None:
        kwargs["padding_setting"] = padding_type.NONE
    try:
        return client.price_timeseries(symbol, **kwargs)
    except TypeError:
        kwargs.pop("padding_setting", None)
        try:
            return client.price_timeseries(symbol, **kwargs)
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None


def discover_delisted_suffixes(
    ticker: str,
    delisted_symbols: list[str],
) -> list[str]:
    """Return ``TICKER-YYYYMM`` matches from an in-memory delisted symbol list.

    The full list must not be written to disk. Only the filtered stem matches
    are returned.
    """
    stem = ticker.strip().upper()
    if not stem:
        return []
    matches: list[str] = []
    seen: set[str] = set()
    for raw in delisted_symbols:
        symbol = str(raw).strip().upper()
        match = _SUFFIX_RE.fullmatch(symbol)
        if match is None:
            continue
        if match.group(1) != stem:
            continue
        if symbol not in seen:
            seen.add(symbol)
            matches.append(symbol)
    return sorted(matches)


def load_delisted_symbols(client: object, *, database: str = DELISTED_DATABASE_NAME) -> list[str]:
    """Fetch delisted symbols in memory. Callers must not persist the full list."""
    fn = getattr(client, "database_symbols", None)
    if not callable(fn):
        return []
    try:
        raw = fn(database)
    except TypeError:
        try:
            raw = fn()
        except Exception:  # noqa: BLE001
            return []
    except Exception:  # noqa: BLE001
        return []
    if raw is None:
        return []
    return [str(item) for item in raw]


def evaluate_package_proof(
    *,
    ndu_running: bool,
    databases: list[str],
    proof_lookups: dict[str, LookupResult],
    delisted_match_count: int,
    errors: list[str],
    norgatedata_importable: bool = True,
) -> PackageProof:
    names = [name.strip() for name in databases]
    listed = _has_database(names, LISTED_DATABASE_NAME)
    delisted = _has_database(names, DELISTED_DATABASE_NAME)
    controls = [
        proof_lookups[symbol]
        for symbol in PACKAGE_PROOF_SYMBOLS
        if symbol in proof_lookups and proof_lookups[symbol].found
    ]
    first_dates = [parse_iso_date(row.first_date) for row in controls]
    history_covers_start = any(item is not None and item <= EVAL_START for item in first_dates)
    starts_after_eval = bool(first_dates) and all(
        item is not None and item > EVAL_START for item in first_dates
    )
    tape_reaches_end = any(_control_reaches_eval_end(row) for row in controls)
    trial_capped = bool(first_dates) and all(
        item == TRIAL_HISTORY_START for item in first_dates if item is not None
    )
    history_precedes_trial_cap = any(
        item is not None and item <= FULL_HISTORY_EVAL_START for item in first_dates
    )
    suffix_hits = sum(
        1
        for suffix in DELISTED_PROBE_SUFFIXES
        if suffix in proof_lookups and proof_lookups[suffix].found
    )
    delisted_populated = suffix_hits > 0 or delisted_match_count > 0
    proof = PackageProof(
        ndu_running=ndu_running,
        norgatedata_importable=norgatedata_importable,
        databases=names,
        delisted_db_present=delisted,
        listed_db_present=listed,
        delisted_populated=delisted_populated,
        delisted_match_count=delisted_match_count + suffix_hits,
        history_precedes_trial_cap=history_precedes_trial_cap,
        trial_capped=trial_capped,
        proof_symbols={
            symbol: {
                "found": "true" if row.found else "false",
                "assetid": row.assetid,
                "first_date": row.first_date,
                "last_date": row.last_date,
                "error": row.error,
            }
            for symbol, row in proof_lookups.items()
        },
        errors=list(errors),
    )
    if not ndu_running or not norgatedata_importable:
        proof.verdict = "NOT_TESTABLE"
        proof.notes = "NDU is not running or norgatedata is not importable."
        return proof
    if starts_after_eval or (first_dates and not history_covers_start):
        proof.verdict = "FAIL"
        proof.notes = (
            "Quoted history starts after 2024-09-03. The 2-year vendor-validation "
            "window requires control first_quoted on or before 2024-09-03."
        )
        return proof
    if not listed or not history_covers_start:
        proof.verdict = "FAIL"
        proof.notes = "US Equities does not cover the 2-year window starting 2024-09-03."
        return proof
    if controls and not tape_reaches_end:
        proof.verdict = "FAIL"
        proof.notes = "Control last_quoted does not reach 2025-12-31 (open tape is allowed)."
        return proof
    proof.verdict = "PASS"
    proof.notes = (
        "Trial-depth 2-year window: first_quoted ≤ 2024-09-03 and tape reaches "
        "2025-12-31. Populated historical Delisted is not required for this gate. "
        "Full Historical Research Ready remains a future Platinum gate."
    )
    return proof


def _control_reaches_eval_end(row: LookupResult) -> bool:
    last = parse_iso_date(row.last_date)
    return last is None or last >= EVAL_END


def _has_database(names: list[str], expected: str) -> bool:
    return any(name.casefold() == expected.casefold() for name in names)


def _series_len(payload: object) -> int:
    if payload is None:
        return 0
    if hasattr(payload, "__len__"):
        try:
            return len(cast(Any, payload))
        except TypeError:
            return 0
    return 0


def _series_differ(left: object, right: object) -> bool | None:
    if left is None or right is None:
        return None
    if _series_len(left) == 0 or _series_len(right) == 0:
        return None
    try:
        return str(left) != str(right)
    except Exception:  # noqa: BLE001
        return None
