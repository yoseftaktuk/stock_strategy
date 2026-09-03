"""PIT occupancy → Norgate assetid mapping. Staged only; no seed writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.norgate_trial.client import LookupResult, NorgateClient, lookup_symbol, parse_iso_date
from app.norgate_trial.constants import (
    EVAL_END,
    EVAL_START,
    OVERLAY_OCCUPANCIES,
    RESEARCH_WINDOW_END,
    RESEARCH_WINDOW_START,
    STATUS_CONFLICT,
    STATUS_MAPPED,
    STATUS_UNRESOLVED,
    TICKER_CHANGE_PAIRS,
)
from app.security_master.interface import SecurityMaster
from app.universe.models import ConstituentMembership


@dataclass(frozen=True)
class Occupancy:
    pit_ticker: str
    occupancy_start: date
    occupancy_end: date | None
    expected_identity: str
    seed_key: str
    overlay: bool = False

    def midpoint(self) -> date:
        start = self.occupancy_start
        end = self.occupancy_end or EVAL_END
        if end < start:
            return start
        delta = (end - start).days
        return start + timedelta(days=delta // 2)

    def contains(self, as_of: date) -> bool:
        if self.occupancy_start > as_of:
            return False
        if self.occupancy_end is None:
            return True
        return as_of < self.occupancy_end

    def eval_start(self) -> date:
        return max(EVAL_START, self.occupancy_start)

    def eval_end(self) -> date:
        if self.occupancy_end is None:
            return EVAL_END
        return min(EVAL_END, self.occupancy_end - timedelta(days=1))

    def overlaps_eval_window(self) -> bool:
        return self.eval_start() <= self.eval_end()


@dataclass
class OccupancyMapping:
    occupancy: Occupancy
    norgate_symbol: str = ""
    norgate_asset_id: str = ""
    security_name: str = ""
    first_quoted: str = ""
    last_quoted: str = ""
    identity_source: str = ""
    mapping_status: str = STATUS_UNRESOLVED
    notes: str = ""
    current_ticker_asset_id: str = ""

    def as_csv_dict(self) -> dict[str, str]:
        occ = self.occupancy
        return {
            "pit_ticker": occ.pit_ticker,
            "occupancy_start": occ.occupancy_start.isoformat(),
            "occupancy_end": "" if occ.occupancy_end is None else occ.occupancy_end.isoformat(),
            "expected_identity": occ.expected_identity,
            "seed_key": occ.seed_key,
            "norgate_symbol": self.norgate_symbol,
            "norgate_asset_id": self.norgate_asset_id,
            "security_name": self.security_name,
            "first_quoted": self.first_quoted,
            "last_quoted": self.last_quoted,
            "identity_source": self.identity_source,
            "mapping_status": self.mapping_status,
            "notes": self.notes,
        }


def provisional_seed_key(ticker: str, start: date, end: date | None) -> str:
    end_token = "open" if end is None else end.isoformat()
    return f"pit:{ticker.upper()}:{start.isoformat()}:{end_token}"


def may_use_current_ticker(occupancy: Occupancy, master: SecurityMaster | None) -> bool:
    """Current ticker is historical identity only if it still names this occupancy."""
    if master is None:
        return occupancy.occupancy_end is None
    then = master.resolve_security(occupancy.pit_ticker, occupancy.midpoint())
    now = master.resolve_security(occupancy.pit_ticker, EVAL_END)
    if then.is_resolved and now.is_resolved:
        then_sec = then.security
        now_sec = now.security
        if then_sec is None or now_sec is None:
            return occupancy.occupancy_end is None
        return then_sec.seed_key == now_sec.seed_key
    if then.is_resolved and not now.is_resolved:
        return False
    return occupancy.occupancy_end is None


def quoted_range_overlaps_occupancy(
    first: str,
    last: str,
    occupancy: Occupancy,
) -> bool:
    first_d = parse_iso_date(first)
    last_d = parse_iso_date(last) or EVAL_END
    if first_d is None:
        return False
    occ_start = occupancy.eval_start()
    occ_end = occupancy.eval_end()
    if occ_start > occ_end:
        return False
    return first_d <= occ_end and last_d >= occ_start


def build_occupancies(
    memberships: list[ConstituentMembership],
    master: SecurityMaster | None,
    *,
    window_start: date = RESEARCH_WINDOW_START,
    window_end: date = RESEARCH_WINDOW_END,
) -> list[Occupancy]:
    rows: list[Occupancy] = []
    seen: set[tuple[str, date, date | None]] = set()
    for item in memberships:
        if not item.overlaps_window(window_start, window_end):
            continue
        key = (item.symbol, item.start_date, item.end_date)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_occupancy_from_membership(item, master))
    for ticker, start, end, identity, seed in OVERLAY_OCCUPANCIES:
        key = (ticker, start, end)
        if key in seen:
            continue
        seen.add(key)
        resolved_seed = seed
        if master is not None:
            resolved = master.resolve_security(ticker, start)
            if resolved.is_resolved and resolved.security is not None:
                resolved_seed = resolved.security.seed_key
                identity = resolved.security.display_name
        rows.append(
            Occupancy(
                pit_ticker=ticker,
                occupancy_start=start,
                occupancy_end=end,
                expected_identity=identity,
                seed_key=resolved_seed or provisional_seed_key(ticker, start, end),
                overlay=True,
            )
        )
    rows.sort(key=lambda row: (row.pit_ticker, row.occupancy_start))
    return rows


def window_ticker_count(occupancies: list[Occupancy]) -> int:
    """Unique non-overlay PIT tickers overlapping the vendor-validation window."""
    return len(
        {
            row.pit_ticker
            for row in occupancies
            if not row.overlay
            and row.occupancy_start <= RESEARCH_WINDOW_END
            and (row.occupancy_end is None or row.occupancy_end > RESEARCH_WINDOW_START)
        }
    )


def frozen_suffix_for(ticker: str, occupancy: Occupancy, suffixes: dict[str, str]) -> str:
    keyed = suffixes.get(f"{ticker}:{occupancy.occupancy_end.isoformat() if occupancy.occupancy_end else 'open'}")
    if keyed:
        return keyed
    return suffixes.get(ticker, "")


def map_occupancy(
    occupancy: Occupancy,
    client: NorgateClient,
    *,
    master: SecurityMaster | None,
    frozen_suffix: str = "",
    discovered_suffixes: list[str] | None = None,
    successor_symbol: str = "",
) -> OccupancyMapping:
    mapping = OccupancyMapping(occupancy=occupancy)
    current = lookup_symbol(client, occupancy.pit_ticker, fetch_bars=False)
    if current.found:
        mapping.current_ticker_asset_id = current.assetid
    allow_current = may_use_current_ticker(occupancy, master)
    notes: list[str] = []
    if occupancy.overlay:
        notes.append("overlay occupancy (not used as PIT universe).")

    if allow_current and current.found:
        _apply_lookup(mapping, current, "current_ticker")
        notes.append("current ticker names this occupancy.")
        mapping.notes = " ".join(notes)
        return mapping
    if current.found and not allow_current:
        notes.append(
            f"current ticker {occupancy.pit_ticker} assetid={current.assetid} "
            "is not historical identity for this occupancy."
        )

    candidates: list[str] = []
    if frozen_suffix:
        candidates.append(frozen_suffix)
    for suffix in discovered_suffixes or ():
        if suffix and suffix not in candidates:
            candidates.append(suffix)
    if successor_symbol and successor_symbol not in candidates:
        candidates.append(successor_symbol)

    hits: list[LookupResult] = []
    for symbol in candidates:
        result = lookup_symbol(client, symbol, fetch_bars=False)
        source = "delisted_suffix" if symbol != successor_symbol else "successor_ticker"
        if symbol == frozen_suffix:
            source = "frozen_suffix"
        if not result.found:
            notes.append(f"{symbol}: NOT_FOUND.")
            continue
        if not quoted_range_overlaps_occupancy(result.first_date, result.last_date, occupancy):
            notes.append(
                f"{symbol} assetid={result.assetid} quoted range does not overlap occupancy."
            )
            continue
        hits.append(result)
        _apply_lookup(mapping, result, source)
        notes.append(f"mapped via {source} {symbol}.")
        break

    if mapping.mapping_status != STATUS_MAPPED and successor_symbol:
        successor = lookup_symbol(client, successor_symbol, fetch_bars=False)
        if successor.found and quoted_range_overlaps_occupancy(
            successor.first_date, successor.last_date, occupancy
        ):
            _apply_lookup(mapping, successor, "successor_ticker")
            notes.append(
                f"predecessor occupancy mapped via successor {successor_symbol} "
                "(ticker-change continuity hypothesis)."
            )

    if mapping.mapping_status != STATUS_MAPPED:
        mapping.mapping_status = STATUS_UNRESOLVED
        notes.append("UNRESOLVED: no occupancy-safe Norgate identity.")
    if len(hits) > 1:
        ids = {item.assetid for item in hits}
        if len(ids) > 1:
            mapping.mapping_status = STATUS_CONFLICT
            notes.append("CONFLICT: multiple assetids for one occupancy.")
    mapping.notes = " ".join(notes).strip()
    return mapping


def successor_for(ticker: str) -> str:
    for predecessor, successor in TICKER_CHANGE_PAIRS:
        if predecessor == ticker:
            return successor
    return ""


def occupancy_for_as_of(mappings: list[OccupancyMapping], ticker: str, as_of: date) -> OccupancyMapping | None:
    matches = [
        row
        for row in mappings
        if row.occupancy.pit_ticker == ticker and row.occupancy.contains(as_of)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def current_ticker_contamination(
    mapping: OccupancyMapping,
    master: SecurityMaster | None,
) -> bool:
    """True when a historical occupancy was mapped to the live ticker wrongly."""
    if mapping.identity_source == "current_ticker" and not may_use_current_ticker(
        mapping.occupancy, master
    ):
        return True
    return False


def _occupancy_from_membership(
    item: ConstituentMembership,
    master: SecurityMaster | None,
) -> Occupancy:
    identity = item.company_name or ""
    seed = provisional_seed_key(item.symbol, item.start_date, item.end_date)
    if master is not None:
        as_of = item.start_date
        if item.end_date is not None:
            as_of = item.start_date + timedelta(days=max((item.end_date - item.start_date).days // 2, 0))
        resolved = master.resolve_security(item.symbol, as_of)
        if resolved.is_resolved and resolved.security is not None:
            seed = resolved.security.seed_key
            identity = resolved.security.display_name
    return Occupancy(
        pit_ticker=item.symbol,
        occupancy_start=item.start_date,
        occupancy_end=item.end_date,
        expected_identity=identity,
        seed_key=seed,
    )


def _apply_lookup(mapping: OccupancyMapping, result: LookupResult, source: str) -> None:
    mapping.norgate_symbol = result.vendor_symbol or result.symbol
    mapping.norgate_asset_id = result.assetid
    mapping.security_name = result.security_name
    mapping.first_quoted = result.first_date
    mapping.last_quoted = result.last_date
    mapping.identity_source = source
    mapping.mapping_status = STATUS_MAPPED
