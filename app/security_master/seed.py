"""Load the evidence-backed known-identities catalog.

The catalog is a static JSON file. It is not a ticker blacklist and does not
download identifier datasets.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.models.security import Security, SecurityIdentifier, SecurityTicker
from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.exceptions import SecurityMasterSourceError

DEFAULT_SEED_PATH = Path("data/security_master/known_identities.json")


def load_known_identities_catalog(
    path: Path | None = None,
) -> InMemorySecurityMaster:
    """Return the in-memory Security Master from the known-identities seed."""
    seed_path = path or DEFAULT_SEED_PATH
    try:
        raw = seed_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecurityMasterSourceError(f"cannot read identity catalog: {seed_path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecurityMasterSourceError(f"invalid identity catalog JSON: {seed_path}") from exc
    if not isinstance(payload, Mapping):
        raise SecurityMasterSourceError("identity catalog must be a JSON object")
    return catalog_from_payload(payload)


def catalog_from_payload(payload: Mapping[str, Any]) -> InMemorySecurityMaster:
    source = str(payload.get("source") or "security-master-seed")
    source_version = str(payload.get("source_version") or "")
    securities: list[Security] = []
    tickers: list[SecurityTicker] = []
    identifiers: list[SecurityIdentifier] = []
    rows = payload.get("securities")
    if not isinstance(rows, list):
        raise SecurityMasterSourceError("identity catalog securities must be a list")
    for item in rows:
        if not isinstance(item, Mapping):
            raise SecurityMasterSourceError("each security must be a JSON object")
        seed_key = str(item.get("seed_key") or "")
        securities.append(
            Security(
                seed_key=seed_key,
                display_name=str(item.get("display_name") or ""),
                security_type=str(item.get("security_type") or "COMMON_STOCK"),
                currency=str(item.get("currency") or "USD"),
                status=str(item.get("status") or "ACTIVE"),
                notes=item.get("notes"),
            )
        )
        for ticker in item.get("tickers") or ():
            if not isinstance(ticker, Mapping):
                raise SecurityMasterSourceError("each ticker must be a JSON object")
            tickers.append(
                SecurityTicker(
                    seed_key=seed_key,
                    scheme=str(ticker.get("scheme") or ""),
                    ticker=str(ticker.get("ticker") or ""),
                    valid_from=_parse_date(ticker.get("valid_from"), field="valid_from"),
                    valid_to=_parse_optional_date(ticker.get("valid_to")),
                    continuity=bool(ticker.get("continuity") or False),
                    source=str(ticker.get("source") or source),
                    source_version=str(ticker.get("source_version") or source_version) or None,
                )
            )
        for identifier in item.get("identifiers") or ():
            if not isinstance(identifier, Mapping):
                raise SecurityMasterSourceError("each identifier must be a JSON object")
            identifiers.append(
                SecurityIdentifier(
                    seed_key=seed_key,
                    id_type=str(identifier.get("id_type") or ""),
                    id_value=str(identifier.get("id_value") or ""),
                    valid_from=_parse_optional_date(identifier.get("valid_from")),
                    valid_to=_parse_optional_date(identifier.get("valid_to")),
                )
            )
    return InMemorySecurityMaster(securities, tickers, identifiers)


def _parse_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise SecurityMasterSourceError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SecurityMasterSourceError(f"{field} is not a valid ISO date: {value}") from exc


def _parse_optional_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    return _parse_date(value, field="date")
