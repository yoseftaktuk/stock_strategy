"""Public historical S&P 500 constituent source adapter.

Source: https://github.com/fja05680/sp500

This is a public reconstruction of S&P 500 membership since 1996. It is NOT an
official S&P Dow Jones Indices data feed. Historical membership accuracy depends
on that source. Ticker changes are not fully solved: the adapter preserves the
source ticker after stripping dataset-only ``-YYYYMM`` removal suffixes.
Share-class punctuation such as ``BRK.B`` is kept as published and is not mapped
to Yahoo Finance ``BRK-B`` form.

The rest of the application must not depend on this CSV schema. Import converts
change-date snapshots into canonical ``[start_date, end_date)`` intervals.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.data.validation import normalize_symbol
from app.universe.exceptions import UniverseSourceError
from app.universe.models import ConstituentMembership

logger = logging.getLogger(__name__)

SOURCE_NAME = "fja05680/sp500"
DEFAULT_CACHE_PATH = Path("data/raw/sp500_historical.csv")
DEFAULT_SOURCE_URLS: tuple[str, ...] = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv",
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes.csv",
)
REQUIRED_COLUMNS = frozenset({"date", "tickers"})
_REMOVAL_SUFFIX = re.compile(r"^(.+)-(\d{6})$")

UniverseFetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class SP500SourceLoad:
    """Normalized membership intervals plus import diagnostics."""

    memberships: tuple[ConstituentMembership, ...]
    raw_records: int
    source: str
    source_version: str
    cache_path: Path | None = None


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "momentum-trader-universe/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
            payload = bytes(response.read())
            return payload
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UniverseSourceError(f"Failed to download historical S&P 500 universe: {exc}") from exc


def normalize_constituent_symbol(raw: str) -> str:
    """Normalize a source ticker consistently with market data.

    Strips dataset-only ``-YYYYMM`` suffixes (for example ``AAL-199702`` → ``AAL``).
    Does not rewrite share-class punctuation (``BRK.B`` stays ``BRK.B``).
    """
    symbol = normalize_symbol(raw)
    match = _REMOVAL_SUFFIX.fullmatch(symbol)
    if match:
        return match.group(1)
    return symbol


def snapshots_to_intervals(
    snapshots: Sequence[tuple[date, frozenset[str]]],
    *,
    source: str = SOURCE_NAME,
    source_version: str | None = None,
) -> list[ConstituentMembership]:
    """Convert ordered change-date snapshots into half-open membership intervals."""
    ordered = sorted(snapshots, key=lambda item: item[0])
    open_starts: dict[str, date] = {}
    previous: set[str] = set()
    closed: list[ConstituentMembership] = []

    for change_date, members in ordered:
        current = set(members)
        for symbol in previous - current:
            start_date = open_starts.pop(symbol)
            closed.append(
                ConstituentMembership(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=change_date,
                    source=source,
                    source_version=source_version,
                )
            )
        for symbol in current - previous:
            open_starts[symbol] = change_date
        previous = current

    for symbol, start_date in open_starts.items():
        closed.append(
            ConstituentMembership(
                symbol=symbol,
                start_date=start_date,
                end_date=None,
                source=source,
                source_version=source_version,
            )
        )
    return closed


class SP500HistoricalSource:
    """Load, parse, and normalize the public fja05680/sp500 dataset."""

    def __init__(
        self,
        *,
        fetcher: UniverseFetcher | None = None,
        cache_path: Path = DEFAULT_CACHE_PATH,
        source_urls: Sequence[str] = DEFAULT_SOURCE_URLS,
    ) -> None:
        self._fetcher = fetcher or download_bytes
        self._cache_path = cache_path
        self._source_urls = tuple(source_urls)

    def load(
        self,
        *,
        source_file: Path | None = None,
        source_url: str | None = None,
    ) -> SP500SourceLoad:
        raw, cache_path = self._read_bytes(source_file=source_file, source_url=source_url)
        source_version = hashlib.sha256(raw).hexdigest()
        snapshots, raw_records = self.parse_snapshots(raw)
        memberships = snapshots_to_intervals(
            snapshots,
            source=SOURCE_NAME,
            source_version=source_version,
        )
        return SP500SourceLoad(
            memberships=tuple(memberships),
            raw_records=raw_records,
            source=SOURCE_NAME,
            source_version=source_version,
            cache_path=cache_path,
        )

    def _read_bytes(
        self,
        *,
        source_file: Path | None,
        source_url: str | None,
    ) -> tuple[bytes, Path | None]:
        if source_file is not None:
            path = Path(source_file)
            if not path.is_file():
                raise UniverseSourceError(f"Universe source file does not exist: {path}")
            return path.read_bytes(), path

        urls = (source_url,) if source_url else self._source_urls
        last_error: Exception | None = None
        for url in urls:
            try:
                payload = self._fetcher(url)
            except UniverseSourceError as exc:
                last_error = exc
                logger.warning("Universe source URL failed: %s", exc)
                continue
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_bytes(payload)
            return payload, self._cache_path

        if last_error is not None:
            raise last_error
        raise UniverseSourceError("No historical S&P 500 source URL was configured")

    def parse_snapshots(self, raw: bytes) -> tuple[list[tuple[date, frozenset[str]]], int]:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise UniverseSourceError("Historical S&P 500 CSV has no header row")
        columns = {name.strip().lower() for name in reader.fieldnames if name}
        if not REQUIRED_COLUMNS.issubset(columns):
            raise UniverseSourceError(
                "Historical S&P 500 CSV schema is invalid; expected columns date,tickers "
                f"got {sorted(columns)}"
            )

        snapshots: list[tuple[date, frozenset[str]]] = []
        seen_dates: set[date] = set()
        raw_records = 0
        for row_number, row in enumerate(reader, start=2):
            raw_records += 1
            mapped = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
            raw_date = mapped.get("date", "")
            raw_tickers = mapped.get("tickers", "")
            if not raw_date:
                raise UniverseSourceError(f"Missing date on row {row_number}")
            change_date = _parse_source_date(raw_date, row_number)
            if change_date in seen_dates:
                raise UniverseSourceError(f"Duplicate snapshot date {change_date.isoformat()} on row {row_number}")
            seen_dates.add(change_date)
            symbols = _parse_tickers(raw_tickers)
            if not symbols:
                raise UniverseSourceError(f"Empty ticker list on row {row_number} date={change_date.isoformat()}")
            snapshots.append((change_date, symbols))

        if not snapshots:
            raise UniverseSourceError("Historical S&P 500 CSV contained no snapshot rows")
        return snapshots, raw_records


def _parse_source_date(value: str, row_number: int) -> date:
    for parser in (
        date.fromisoformat,
        lambda text: datetime.strptime(text, "%Y-%m-%d").date(),
        lambda text: datetime.strptime(text, "%m/%d/%Y").date(),
        lambda text: datetime.strptime(text, "%m-%d-%Y").date(),
    ):
        try:
            return parser(value)
        except ValueError:
            continue
    raise UniverseSourceError(f"Invalid date {value!r} on row {row_number}")


def _parse_tickers(raw_tickers: str) -> frozenset[str]:
    symbols: set[str] = set()
    for token in raw_tickers.split(","):
        cleaned = token.strip().strip('"').strip("'")
        if not cleaned:
            continue
        symbols.add(normalize_constituent_symbol(cleaned))
    return frozenset(symbols)
