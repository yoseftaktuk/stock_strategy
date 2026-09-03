"""Staged Norgate bars in MarketBar CSV shape. Isolated from market_bars."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.data.validation import ParsedBar, validate_historical_parsed_bar
from app.norgate_trial.client import parse_iso_date
from app.norgate_trial.constants import BAR_CSV_FIELDS, EVAL_END, MAX_INTERIOR_GAP_DAYS
from app.norgate_trial.occupancy import Occupancy
from app.norgate_trial.paths import assert_trial_output_dir


@dataclass(frozen=True)
class StagedBar:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: int


def bars_from_timeseries(symbol: str, payload: object, *, adjusted: bool) -> list[StagedBar]:
    rows: list[StagedBar] = []
    for raw in _iter_records(payload):
        bar = _record_to_bar(symbol, raw, adjusted=adjusted)
        if bar is not None:
            rows.append(bar)
    rows.sort(key=lambda item: item.timestamp)
    return rows


def write_bar_csv(path: Path, bars: Sequence[StagedBar]) -> None:
    assert_trial_output_dir(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BAR_CSV_FIELDS)
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "adjusted_close": "" if bar.adjusted_close is None else str(bar.adjusted_close),
                    "volume": str(bar.volume),
                }
            )


def read_bar_csv(path: Path) -> list[StagedBar]:
    if not path.is_file():
        return []
    rows: list[StagedBar] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            timestamp = _parse_timestamp(item.get("timestamp") or "")
            if timestamp is None:
                continue
            adjusted = _decimal(item.get("adjusted_close") or "")
            rows.append(
                StagedBar(
                    symbol=(item.get("symbol") or "").strip(),
                    timestamp=timestamp,
                    open=_decimal(item.get("open") or "0") or Decimal("0"),
                    high=_decimal(item.get("high") or "0") or Decimal("0"),
                    low=_decimal(item.get("low") or "0") or Decimal("0"),
                    close=_decimal(item.get("close") or "0") or Decimal("0"),
                    adjusted_close=adjusted,
                    volume=int(item.get("volume") or "0"),
                )
            )
    return rows


def validate_staged_bars(bars: Sequence[StagedBar], *, require_adjusted: bool) -> list[str]:
    issues: list[str] = []
    for index, bar in enumerate(bars, start=1):
        parsed = ParsedBar(
            symbol=bar.symbol,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adjusted_close=bar.adjusted_close,
            volume=bar.volume,
            row_number=index,
            source="norgate_platinum_trial",
        )
        if require_adjusted:
            for issue in validate_historical_parsed_bar(parsed):
                issues.append(issue.format())
        else:
            if bar.timestamp.tzinfo is None:
                issues.append(f"row={index} timestamp must be timezone-aware")
            if bar.close < 0 or bar.volume < 0:
                issues.append(f"row={index} negative close or volume")
    return issues


def interior_gaps(bars: Sequence[StagedBar], occupancy: Occupancy) -> list[str]:
    if len(bars) < 2:
        return []
    gaps: list[str] = []
    ordered = sorted(bars, key=lambda item: item.timestamp)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        delta = (current.timestamp.date() - previous.timestamp.date()).days
        if delta > MAX_INTERIOR_GAP_DAYS:
            gaps.append(
                f"{previous.timestamp.date().isoformat()} → {current.timestamp.date().isoformat()} "
                f"({delta} days)"
            )
    return gaps


def series_cover_occupancy(bars: Sequence[StagedBar], occupancy: Occupancy) -> bool:
    if not bars:
        return False
    first = min(item.timestamp.date() for item in bars)
    last = max(item.timestamp.date() for item in bars)
    return first <= occupancy.eval_start() and last >= occupancy.eval_end()


def totalreturn_differs(totalreturn: Sequence[StagedBar], unadjusted: Sequence[StagedBar]) -> bool | None:
    if not totalreturn or not unadjusted:
        return None
    by_day_tr = {item.timestamp.date(): item.close for item in totalreturn}
    by_day_raw = {item.timestamp.date(): item.close for item in unadjusted}
    shared = set(by_day_tr) & set(by_day_raw)
    if not shared:
        return None
    return any(by_day_tr[day] != by_day_raw[day] for day in shared)


def clip_to_occupancy(bars: Sequence[StagedBar], occupancy: Occupancy) -> list[StagedBar]:
    start = occupancy.eval_start()
    end = occupancy.eval_end()
    return [item for item in bars if start <= item.timestamp.date() <= end]


def _iter_records(payload: object) -> Iterable[dict[str, object]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        rows: list[dict[str, object]] = []
        for item in payload:
            if isinstance(item, dict):
                rows.append(item)
        return rows
    to_dict = getattr(payload, "to_dict", None)
    if callable(to_dict):
        try:
            orient = to_dict(orient="index")
        except TypeError:
            orient = None
        if isinstance(orient, dict):
            records: list[dict[str, object]] = []
            for key, values in orient.items():
                row = dict(values) if isinstance(values, dict) else {"Close": values}
                row.setdefault("Date", key)
                records.append(row)
            return records
    return []


def _record_to_bar(symbol: str, raw: dict[str, object], *, adjusted: bool) -> StagedBar | None:
    when = raw.get("Date") or raw.get("date") or raw.get("timestamp")
    timestamp = _coerce_timestamp(when)
    if timestamp is None:
        return None
    close = _decimal(raw.get("Close") or raw.get("close"))
    unadjusted = _decimal(raw.get("Unadjusted Close") or raw.get("unadjusted_close"))
    open_px = _decimal(raw.get("Open") or raw.get("open")) or close
    high = _decimal(raw.get("High") or raw.get("high")) or close
    low = _decimal(raw.get("Low") or raw.get("low")) or close
    volume_raw = raw.get("Volume") or raw.get("volume") or 0
    volume = 0
    if isinstance(volume_raw, bool):
        volume = int(volume_raw)
    elif isinstance(volume_raw, int):
        volume = volume_raw
    elif isinstance(volume_raw, float):
        volume = int(volume_raw)
    elif isinstance(volume_raw, str) and volume_raw.strip():
        try:
            volume = int(float(volume_raw))
        except ValueError:
            volume = 0
    if close is None:
        return None
    if adjusted:
        close_px = unadjusted if unadjusted is not None else close
        adjusted_close = close
    else:
        close_px = close
        adjusted_close = None
    if open_px is None or high is None or low is None:
        return None
    return StagedBar(
        symbol=symbol,
        timestamp=timestamp,
        open=open_px,
        high=high,
        low=low,
        close=close_px,
        adjusted_close=adjusted_close,
        volume=volume,
    )


def _coerce_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    parsed = parse_iso_date(str(value))
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        day = parse_iso_date(text)
        if day is None:
            return None
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", ""}:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def expected_last_session(occupancy: Occupancy) -> date:
    end = occupancy.eval_end()
    return min(end, EVAL_END)


def session_after(day: date, days: int) -> date:
    return day + timedelta(days=days)
