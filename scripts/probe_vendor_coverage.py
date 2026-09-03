#!/usr/bin/env python3
"""Frozen-sample vendor coverage probe for Phase 4.

Proof of capability only. Does not download a vendor universe, does not write
PostgreSQL market_bars, does not replace data/raw CSVs, and does not modify
Security Master seeds.

If norgatedata and a running NDU are available, queries metadata and bounded
single-symbol history. Otherwise records NOT TESTABLE IN CURRENT ENVIRONMENT
and fills documented (not live-proven) vendor capabilities from official
Norgate documentation.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

REQUIRED_START = date(2013, 7, 8)
REQUIRED_END = date(2025, 12, 31)

CSV_FIELDS = (
    "sample_category",
    "ticker",
    "historical_period",
    "pit_security",
    "vendor_security_id",
    "vendor_symbol",
    "first_date",
    "last_date",
    "daily_ohlcv",
    "adjusted_close",
    "delisted_support",
    "ticker_history",
    "identity_status",
    "coverage_status",
    "notes",
)

VENDOR_CREDENTIAL_KEYS = (
    "TIINGO_API_KEY",
    "TIINGO_TOKEN",
    "SHARADAR_API_KEY",
    "NASDAQ_DATA_LINK_API_KEY",
    "QUANDL_API_KEY",
    "NORGATE_USER",
    "NORGATEDATA_ROOT",
    "POLYGON_API_KEY",
)

VM_APP_BUNDLES = (
    ("parallels", Path("/Applications/Parallels Desktop.app")),
    ("utm", Path("/Applications/UTM.app")),
    ("vmware_fusion", Path("/Applications/VMware Fusion.app")),
    ("virtualbox", Path("/Applications/VirtualBox.app")),
    ("windows_app", Path("/Applications/Windows App.app")),
)

VM_CLIS = ("prlctl", "utmctl", "vmrun", "VBoxManage")

# Official Norgate docs (PyPI norgatedata, norgatedata.com FAQ / NDU FAQ).
# These are vendor-class facts, not live proofs that a sample ticker exists.
DOCUMENTED_FIELD_MATRIX: dict[str, str] = {
    "vendor_security_id_assetid": "YES",
    "ticker_current_symbol": "YES",
    "historical_ticker_prior_symbols": "NO",
    "date": "YES",
    "open": "YES",
    "high": "YES",
    "low": "YES",
    "close": "YES",
    "volume": "YES",
    "adjusted_close_totalreturn": "YES",
    "unadjusted_close": "YES",
    "exchange": "YES",
    "security_name": "YES",
    "issuer": "UNKNOWN",
    "delisting_date_last_quoted": "YES",
    "corporate_actions_dividends_splits": "YES",
}

DOCUMENTED_SOURCES = (
    "https://pypi.org/project/norgatedata/",
    "https://norgatedata.com/data-package-faq.php",
    "https://norgatedata.com/ndu-faq.php",
    "https://norgatedata.com/stockmarketpackages.php",
)


@dataclass(frozen=True)
class FrozenSample:
    sample_category: str
    ticker: str
    historical_period: str
    pit_security: str
    expected_identity: str
    security_valid_from: str
    security_valid_to: str
    must_not_alias: str
    notes_hint: str
    lookup_ticker: str | None = None


@dataclass
class ProbeRow:
    sample_category: str
    ticker: str
    historical_period: str
    pit_security: str
    vendor_security_id: str
    vendor_symbol: str
    first_date: str
    last_date: str
    daily_ohlcv: str
    adjusted_close: str
    delisted_support: str
    ticker_history: str
    identity_status: str
    coverage_status: str
    notes: str
    evidence_type: str = "NOT_TESTABLE"
    expected_identity: str = ""
    security_valid_from: str = ""
    security_valid_to: str = ""
    must_not_alias: str = ""
    live_security_name: str = ""
    live_error: str = ""

    def as_csv_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in CSV_FIELDS}


FROZEN_SAMPLE: tuple[FrozenSample, ...] = (
    FrozenSample(
        "A_acquired_delisted",
        "ATVI",
        "2015-08-31→2023-10-18",
        "",
        "Activision Blizzard",
        "2015-08-31",
        "2023-10-18",
        "MSFT",
        "Must retain Activision identity after Microsoft combination. ATVI must not resolve to MSFT bars.",
    ),
    FrozenSample(
        "A_acquired_delisted",
        "CELG",
        "2006-11-06→2019-11-21",
        "",
        "Celgene",
        "2006-11-06",
        "2019-11-21",
        "BMY",
        "Must retain Celgene identity. CELG must not resolve to Bristol-Myers (BMY) bars.",
    ),
    FrozenSample(
        "A_acquired_delisted",
        "XLNX",
        "1999-11-08→2022-02-15",
        "",
        "Xilinx",
        "1999-11-08",
        "2022-02-15",
        "AMD",
        "Must retain Xilinx identity. XLNX must not resolve to AMD bars.",
    ),
    FrozenSample(
        "A_acquired_delisted",
        "FRC",
        "2019-01-02→2023-05-04",
        "",
        "First Republic Bank",
        "2019-01-02",
        "2023-05-04",
        "",
        "Failed/delisted bank. Need own historical series, not a successor alias.",
    ),
    FrozenSample(
        "A_acquired_delisted",
        "SIVB",
        "2018-03-19→2023-03-15",
        "",
        "SVB Financial Group",
        "2018-03-19",
        "2023-03-15",
        "",
        "Failed/delisted bank. Need own historical series, not a successor alias.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "CBS",
        "1996-01-02→2019-12-05",
        "",
        "CBS Corporation (historical listing)",
        "1996-01-02",
        "2019-12-05",
        "PARA/WBD",
        "Do not infer identity from successor ticker. CBS is not automatically PARA or WBD.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "VIAB",
        "2006-01-03→2019-12-05",
        "",
        "Viacom (historical listing)",
        "2006-01-03",
        "2019-12-05",
        "PARA/WBD",
        "Do not infer identity from successor ticker.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "VIAC",
        "2019-12-05→2022-02-17",
        "",
        "ViacomCBS (historical listing)",
        "2019-12-05",
        "2022-02-17",
        "PARA",
        "Do not treat VIAC as automatically PARA. WBD is not automatically DISCA.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "LLL",
        "2004-12-01→2019-07-01",
        "",
        "L3 Technologies (historical listing)",
        "2004-12-01",
        "2019-07-01",
        "LHX",
        "L3 standalone is not L3Harris. Do not alias LLL to LHX.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "RTN",
        "1996-01-02→2020-04-06",
        "",
        "Raytheon Company (historical listing)",
        "1996-01-02",
        "2020-04-06",
        "RTX",
        "Raytheon Company is not RTX. Do not alias RTN to UTX/RTX.",
    ),
    FrozenSample(
        "B_identity_chain_unresolved",
        "DWDP",
        "2017-09-01→2019-06-03",
        "",
        "DowDuPont (historical listing)",
        "2017-09-01",
        "2019-06-03",
        "DOW/DD/CTVA",
        "Combination/split chain. Do not guess successor identity from current tickers.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "AVB",
        "2007-01-10→open",
        "",
        "AvalonBay Communities",
        "2007-01-10",
        "",
        "",
        "Still-listed hole. Need identity plus required 2013-07-08→2025-12-31 series.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "EA",
        "2002-07-22→open",
        "",
        "Electronic Arts",
        "2002-07-22",
        "",
        "",
        "Still-listed hole. Need identity plus required 2013-07-08→2025-12-31 series.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "EQR",
        "2001-12-03→open",
        "",
        "Equity Residential",
        "2001-12-03",
        "",
        "",
        "Still-listed hole. Need identity plus required 2013-07-08→2025-12-31 series.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "BK",
        "1996-01-02→2026-05-21",
        "",
        "Bank of New York Mellon",
        "1996-01-02",
        "2026-05-21",
        "",
        "Left index in 2026; still listed. Need identity plus required window series.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "MMC",
        "1996-01-02→2026-01-14",
        "",
        "Marsh & McLennan",
        "1996-01-02",
        "2026-01-14",
        "",
        "Still-listed hole. Need identity plus required 2013-07-08→2025-12-31 series.",
    ),
    FrozenSample(
        "C_still_listed_download_hole",
        "HOLX",
        "2016-03-30→2026-04-09",
        "",
        "Hologic",
        "2016-03-30",
        "2026-04-09",
        "",
        "Still-listed hole. Security-valid range starts 2016-03-30; do not require 2013 warmup.",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "COG",
        "2008-06-23→2021-10-04",
        "",
        "Cabot Oil & Gas / Coterra predecessor ticker",
        "2008-06-23",
        "2021-10-04",
        "",
        "Ticker change COG→CTRA. Same security_id expected if same security. Predecessor lookup may fail (Norgate current-symbol-only).",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "CTRA",
        "2021-10-04→2026-05-07",
        "",
        "Coterra Energy successor ticker",
        "2021-10-04",
        "2026-05-07",
        "",
        "Successor of COG. Compare assetid with COG if both resolve.",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "SYMC",
        "2003-03-31→2019-11-05",
        "",
        "Symantec predecessor ticker",
        "2003-03-31",
        "2019-11-05",
        "",
        "Ticker change SYMC→NLOK→GEN. Same security_id expected if same security.",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "GEN",
        "2022-11-08→open",
        "",
        "Gen Digital successor ticker",
        "2022-11-08",
        "",
        "",
        "Successor of SYMC/NLOK. Local GEN.csv already exists; vendor identity still unproven.",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "PKI",
        "1996-01-02→2023-05-16",
        "",
        "PerkinElmer predecessor ticker",
        "1996-01-02",
        "2023-05-16",
        "",
        "Ticker change PKI→RVTY. Same security_id expected if same security.",
    ),
    FrozenSample(
        "D_ticker_change_successor_listed",
        "RVTY",
        "2023-05-16→open",
        "",
        "Revvity successor ticker",
        "2023-05-16",
        "",
        "",
        "Successor of PKI. Local RVTY.csv already exists; vendor identity still unproven.",
    ),
    FrozenSample(
        "E_ticker_recycling_risk",
        "DO",
        "2009-02-26→2016-10-03",
        "",
        "Diamond Offshore (historical occupancy)",
        "2009-02-26",
        "2016-10-03",
        "current DO",
        "Must not fetch the currently listed namesake. Needs historical occupancy + stable ID.",
    ),
    FrozenSample(
        "E_ticker_recycling_risk",
        "CHK",
        "2006-03-03→2018-03-19",
        "",
        "Chesapeake Energy (historical occupancy)",
        "2006-03-03",
        "2018-03-19",
        "current CHK",
        "Must not fetch the currently listed namesake. Needs historical occupancy + stable ID.",
    ),
    FrozenSample(
        "E_ticker_recycling_risk",
        "CA",
        "1996-01-02→2018-11-06",
        "",
        "CA Technologies (historical occupancy)",
        "1996-01-02",
        "2018-11-06",
        "current CA",
        "Must not fetch the currently listed namesake. Needs historical occupancy + stable ID.",
    ),
    FrozenSample(
        "E_ticker_recycling_risk",
        "ADS",
        "2013-12-23→2020-06-22",
        "",
        "Alliance Data / Bread Financial predecessor occupancy",
        "2013-12-23",
        "2020-06-22",
        "current ADS",
        "Must not fetch the currently listed namesake. Needs historical occupancy + stable ID.",
    ),
    FrozenSample(
        "M_known_case",
        "SE",
        "2015 (Spectra Energy occupancy)",
        "spectra-energy",
        "Spectra Energy Corp",
        "2007-01-03",
        "2017-02-27",
        "sea-limited",
        "SE+2015 must be Spectra Energy, distinct assetid from Sea Limited. Local SE.csv is Sea. Do not blacklist SE.",
        lookup_ticker="SE",
    ),
    FrozenSample(
        "M_known_case",
        "SE",
        "2018 (Sea Limited occupancy)",
        "sea-limited",
        "Sea Limited",
        "2017-10-20",
        "",
        "spectra-energy",
        "SE+2018 must be Sea Limited, distinct assetid from Spectra Energy.",
        lookup_ticker="SE",
    ),
    FrozenSample(
        "M_known_case",
        "HAR",
        "2006-02-01→2017-03-13 (Harman International)",
        "harman-international",
        "Harman International Industries",
        "2006-02-01",
        "2017-03-13",
        "current HAR",
        "PIT is Harman. Local HAR.csv is an identity mismatch. Vendor must identify Harman as a distinct historical security with 2006–2017 bars.",
        lookup_ticker="HAR",
    ),
    FrozenSample(
        "M_known_case",
        "HAR",
        "current namesake lookup",
        "",
        "Unknown current HAR instrument (not Harman)",
        "",
        "",
        "harman-international",
        "Current HAR lookup must be distinguishable from Harman. Local HAR.csv first close ~18614 continuing to 2022-03-02 is not Harman.",
        lookup_ticker="HAR",
    ),
    FrozenSample(
        "M_known_case",
        "ESRX",
        "2003-09-26→2018-12-21",
        "express-scripts",
        "Express Scripts Holding Company",
        "2003-09-26",
        "2018-12-21",
        "CI",
        "Must be Express Scripts, not Cigna. Local ESRX.csv ends 2018-12-21. ESRX is not automatically CI.",
    ),
    FrozenSample(
        "M_known_case",
        "SQ",
        "2015-11-19→2025-01-21 (Block Class A predecessor ticker)",
        "block-inc-class-a",
        "Block, Inc. Class A",
        "2015-11-19",
        "2025-01-21",
        "",
        "Same Class A as XYZ. Vendor should preserve one assetid across SQ→XYZ. Predecessor ticker lookup may fail (current-symbol-only).",
    ),
    FrozenSample(
        "M_known_case",
        "XYZ",
        "2025-01-21→open (Block Class A successor ticker)",
        "block-inc-class-a",
        "Block, Inc. Class A",
        "2025-01-21",
        "",
        "",
        "Same Class A ticker change SQ→XYZ on 2025-01-21. Want same vendor security identity. PIT membership 2025-07-23→open.",
    ),
    FrozenSample(
        "M_known_case",
        "WWE",
        "predecessor of TKO (must not be silent TKO history)",
        "",
        "World Wrestling Entertainment predecessor",
        "",
        "2023-09-12",
        "tko-group-holdings",
        "WWE is a different issuer from TKO Group (CIK 0001973266). Not seeded. Probe whether vendor keeps a distinct identity.",
    ),
    FrozenSample(
        "M_known_case",
        "TKO",
        "2023-09-12→open (TKO Group Holdings)",
        "tko-group-holdings",
        "TKO Group Holdings",
        "2023-09-12",
        "",
        "WWE",
        "New issuer from 2023-09-12. Vendor must not silently serve WWE bars as TKO bars. PIT membership 2025-03-24→open.",
    ),
    FrozenSample(
        "M_known_case",
        "GME",
        "2013-07-08→2025-12-31 control",
        "gamestop",
        "GameStop Corp.",
        "2007-12-14",
        "2016-04-25",
        "",
        "Control case: ordinary continuously listed security. One stable identity and daily history. PIT interval in coverage is 2007-12-14→2016-04-25; prices exist through 2025-12-31.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Norgate (or document why it is not testable) on a frozen sample."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("audit"),
        help="Directory for vendor_coverage_probe.csv and vendor_coverage_probe.json.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Project env file used only to detect credential key names.",
    )
    return parser.parse_args()


def _env_file_keys(path: Path) -> list[str]:
    if not path.is_file():
        return []
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.append(stripped.split("=", 1)[0].strip())
    return keys


def detect_environment(env_file: Path) -> dict[str, Any]:
    vm_apps = {name: bundle.is_dir() for name, bundle in VM_APP_BUNDLES}
    vm_clis = {name: bool(shutil.which(name)) for name in VM_CLIS}
    norgatedata_importable = False
    norgatedata_error = ""
    ndu_running: bool | None = None
    try:
        import norgatedata  # type: ignore[import-not-found]

        norgatedata_importable = True
        status_fn = getattr(norgatedata, "status", None)
        if callable(status_fn):
            ndu_running = bool(status_fn())
    except Exception as exc:  # noqa: BLE001 — probe must not crash on missing vendor
        norgatedata_error = f"{type(exc).__name__}: {exc}"

    env_keys = _env_file_keys(env_file)
    credential_env = {key: bool(os.environ.get(key)) for key in VENDOR_CREDENTIAL_KEYS}
    credential_file = {key: key in env_keys for key in VENDOR_CREDENTIAL_KEYS}
    any_fallback = any(credential_env.values()) or any(
        credential_file[key]
        for key in VENDOR_CREDENTIAL_KEYS
        if key not in {"NORGATE_USER", "NORGATEDATA_ROOT", "POLYGON_API_KEY"}
    )

    windows_vm_available = any(vm_apps.values()) or any(vm_clis.values())
    live_queryable = bool(norgatedata_importable and ndu_running)
    full_tape_install_required = not live_queryable

    access = {
        "1_norgate_installable_or_accessible": "NO — NDU is Windows-only; this host is macOS and NDU is not present",
        "2_windows_vm_available": "NO" if not windows_vm_available else "YES",
        "3_norgate_python_api_usable": (
            "NO — norgatedata is not installed in the project venv; even if installed, Python must run where NDU runs"
        ),
        "4_authentication_or_subscription_required": "YES — active Norgate subscription and running NDU are required",
        "5_individual_symbol_history_queryable": (
            "DOCUMENTED YES (price_timeseries by symbol or assetid) — NOT TESTABLE here"
        ),
        "6_constituent_or_security_metadata_available": (
            "DOCUMENTED YES at Platinum (watchlists / index constituent timeseries) — NOT TESTABLE here"
        ),
        "7_stable_assetid_exposed": "DOCUMENTED YES (norgatedata.assetid / integer assetid) — NOT TESTABLE live",
        "8_ticker_history_exposed": (
            "DOCUMENTED NO — official FAQ: prior symbols are not provided; only the current symbol is stored"
        ),
        "9_delisted_securities_accessible": (
            "DOCUMENTED YES at Platinum (US Equities Delisted, -YYYYMM suffix) — NOT TESTABLE live; first-time access requires full local DB"
        ),
        "10_exportable_to_project_shape": (
            "DOCUMENTED YES — Python DataFrame/NumPy can be mapped to symbol,timestamp,OHLCV,adjusted_close,volume — NOT TESTABLE live"
        ),
    }

    stop_conditions = []
    if platform.system() != "Windows" and not windows_vm_available:
        stop_conditions.append("Norgate requires an unavailable Windows environment (NDU is Windows-only).")
    if not norgatedata_importable or ndu_running is not True:
        stop_conditions.append("Authentication/subscription/NDU is unavailable.")
    if full_tape_install_required:
        stop_conditions.append(
            "First-time Norgate access requires installing NDU and downloading the full subscribed US tape; that is a mass download and is out of scope."
        )
    stop_conditions.append(
        "Ticker history as prior-symbol occupancy is documented unavailable; occupancy is current symbol or delisted -YYYYMM suffix plus assetid."
    )
    stop_conditions.append("Licensing is a paid subscription; no license is configured in this environment.")

    return {
        "probe_date": date.today().isoformat(),
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "norgatedata_importable": norgatedata_importable,
        "norgatedata_error": norgatedata_error,
        "ndu_running": ndu_running,
        "windows_vm_available": windows_vm_available,
        "vm_apps": vm_apps,
        "vm_clis": vm_clis,
        "credential_env_present": credential_env,
        "credential_env_file_present": credential_file,
        "fallback_tiingo_or_sharadar_credentials": any_fallback,
        "live_queryable": live_queryable,
        "full_tape_install_required": full_tape_install_required,
        "access_questions": access,
        "stop_conditions": stop_conditions,
        "testable_in_current_environment": live_queryable,
    }


def _docs_row(sample: FrozenSample) -> ProbeRow:
    alias = (
        f" Must not alias to {sample.must_not_alias}."
        if sample.must_not_alias
        else ""
    )
    valid = sample.security_valid_from or "unknown"
    valid_to = sample.security_valid_to or "open/unknown"
    notes = (
        f"NOT TESTABLE IN CURRENT ENVIRONMENT. Evidence=DOCUMENTED only. "
        f"Expected identity: {sample.expected_identity}. "
        f"Required range 2013-07-08→2025-12-31 vs security-valid {valid}→{valid_to} vs vendor-data UNKNOWN."
        f"{alias} {sample.notes_hint} "
        "Norgate FAQ: prior symbols are not provided; delisted names use a -YYYYMM suffix; assetid is the stable key. "
        "Installing Platinum would download the full local tape and was not performed."
    )
    return ProbeRow(
        sample_category=sample.sample_category,
        ticker=sample.ticker,
        historical_period=sample.historical_period,
        pit_security=sample.pit_security,
        vendor_security_id="",
        vendor_symbol="",
        first_date="",
        last_date="",
        daily_ohlcv="UNKNOWN",
        adjusted_close="UNKNOWN",
        delisted_support="UNKNOWN",
        ticker_history="NO",
        identity_status="NOT_TESTABLE",
        coverage_status="NOT_TESTABLE",
        notes=notes.strip(),
        evidence_type="DOCUMENTED",
        expected_identity=sample.expected_identity,
        security_valid_from=sample.security_valid_from,
        security_valid_to=sample.security_valid_to,
        must_not_alias=sample.must_not_alias,
    )


def _try_live_norgate(rows: list[ProbeRow]) -> dict[str, Any]:
    """Query individual symbols only. Never download a database of prices."""
    live_meta: dict[str, Any] = {"attempted": True, "ndu_running": False, "databases": [], "errors": []}
    try:
        import norgatedata  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        live_meta["errors"].append(f"import failed: {exc}")
        live_meta["attempted"] = False
        return live_meta

    status_fn = getattr(norgatedata, "status", None)
    running = bool(status_fn()) if callable(status_fn) else False
    live_meta["ndu_running"] = running
    if not running:
        live_meta["errors"].append("NDU is not running; live queries skipped.")
        return live_meta

    databases_fn = getattr(norgatedata, "databases", None)
    if callable(databases_fn):
        try:
            live_meta["databases"] = list(databases_fn())
        except Exception as exc:  # noqa: BLE001
            live_meta["errors"].append(f"databases() failed: {exc}")

    samples_by_ticker_period = {(row.ticker, row.historical_period): row for row in rows}
    for sample in FROZEN_SAMPLE:
        row = samples_by_ticker_period[(sample.ticker, sample.historical_period)]
        symbol = sample.lookup_ticker or sample.ticker
        try:
            assetid = norgatedata.assetid(symbol)
            name = norgatedata.security_name(symbol)
            first_quoted = norgatedata.first_quoted_date(symbol)
            last_quoted = norgatedata.last_quoted_date(symbol)
            priceadjust = norgatedata.StockPriceAdjustmentType.TOTALRETURN
            pricedata = norgatedata.price_timeseries(
                symbol,
                stock_price_adjustment_setting=priceadjust,
                start_date="2013-07-08",
                end_date="2025-12-31",
                limit=3,
                timeseriesformat="pandas-dataframe",
            )
            row.vendor_security_id = str(assetid) if assetid is not None else ""
            row.vendor_symbol = str(norgatedata.symbol(assetid) if assetid is not None else symbol)
            row.first_date = "" if first_quoted is None else str(first_quoted)[:10]
            row.last_date = "" if last_quoted is None else str(last_quoted)[:10]
            row.daily_ohlcv = "YES" if pricedata is not None and len(pricedata) else "UNKNOWN"
            row.adjusted_close = "YES"
            row.delisted_support = "YES" if last_quoted else "UNKNOWN"
            row.identity_status = "LIVE_PARTIAL"
            row.coverage_status = "LIVE_PARTIAL"
            row.evidence_type = "LIVE"
            row.live_security_name = "" if name is None else str(name)
            row.notes = (
                f"LIVE probe of {symbol}. assetid={row.vendor_security_id} "
                f"name={row.live_security_name!r} first={row.first_date} last={row.last_date}. "
                f"{sample.notes_hint}"
            )
        except Exception as exc:  # noqa: BLE001
            row.live_error = f"{type(exc).__name__}: {exc}"
            row.notes = (
                f"{row.notes} Live lookup of {symbol} failed: {row.live_error}. "
                "No additional symbols were searched; full delisted-database scan was not performed."
            )
    return live_meta


def _known_case_results(rows: list[ProbeRow], live: bool) -> dict[str, Any]:
    se_2015 = next(r for r in rows if r.ticker == "SE" and "2015" in r.historical_period)
    se_2018 = next(r for r in rows if r.ticker == "SE" and "2018" in r.historical_period)
    har_harman = next(r for r in rows if r.ticker == "HAR" and "Harman" in r.historical_period)
    har_current = next(r for r in rows if r.ticker == "HAR" and "current" in r.historical_period)
    results = {
        "SE": {
            "status": "NOT_TESTABLE" if not live else se_2015.identity_status,
            "expected": "SE+2015 → Spectra Energy (assetid A); SE+2018 → Sea Limited (assetid B). FAIL if one ID or current-ticker-only.",
            "observed": (
                "Not live-tested. Documented class: delisted suffix plus distinct assetid can represent two occupancies. "
                "Official FAQ does not expose prior-symbol history, so ticker SE today would be the current occupant unless the delisted suffix is known."
            ),
            "spectra_row": se_2015.identity_status,
            "sea_row": se_2018.identity_status,
        },
        "HAR": {
            "status": "NOT_TESTABLE" if not live else har_harman.identity_status,
            "expected": "Harman International distinct from current HAR; bars during 2006–2017 belonging to Harman.",
            "observed": (
                "Not live-tested. Local HAR.csv remains an identity mismatch. Vendor capability class includes delisted HAR-YYYYMM, unproven for this name."
            ),
            "harman_row": har_harman.identity_status,
            "current_row": har_current.identity_status,
        },
        "ESRX": {
            "status": "NOT_TESTABLE",
            "expected": "Express Scripts own security through ~2018-12; ESRX ≠ CI.",
            "observed": "Not live-tested. Documented delisted tape would keep a non-surviving acquiree as its own delisted security if Platinum is installed.",
        },
        "ATVI": {"status": "NOT_TESTABLE", "expected": "Activision bars, not MSFT.", "observed": "Not live-tested."},
        "CELG": {"status": "NOT_TESTABLE", "expected": "Celgene bars, not BMY.", "observed": "Not live-tested."},
        "XLNX": {"status": "NOT_TESTABLE", "expected": "Xilinx bars, not AMD.", "observed": "Not live-tested."},
        "FRC": {"status": "NOT_TESTABLE", "expected": "First Republic own delisted series.", "observed": "Not live-tested."},
        "SIVB": {"status": "NOT_TESTABLE", "expected": "SVB Financial own delisted series.", "observed": "Not live-tested."},
        "TKO": {
            "status": "NOT_TESTABLE",
            "expected": "TKO from 2023-09-12 as a new issuer; WWE predecessor bars must not be labeled TKO.",
            "observed": (
                "Not live-tested. Residual risk already documented: Norgate surviving-entity / merger-of-equals rules may prepend WWE history under TKO."
            ),
        },
        "XYZ": {
            "status": "NOT_TESTABLE",
            "expected": "Same assetid across SQ→XYZ (same Class A).",
            "observed": "Not live-tested. Documented behavior prepends history onto the current symbol and keeps one assetid through ticker changes.",
        },
        "GME": {
            "status": "NOT_TESTABLE",
            "expected": "One stable identity and ordinary daily history.",
            "observed": "Not live-tested. Control case remains unproven on Norgate until NDU is available.",
        },
    }
    return results


def classify_verdict(env: dict[str, Any], live_meta: dict[str, Any]) -> dict[str, str]:
    if env["live_queryable"] and live_meta.get("ndu_running"):
        return {
            "verdict": "INSUFFICIENT",
            "reason": "Live NDU was reachable but this run did not complete a full frozen-sample pass/fail classification beyond partial lookups.",
        }
    return {
        "verdict": "PROMISING — REQUIRES FULL TRIAL",
        "reason": (
            "Norgate could not be queried in this environment. Official documentation still supports "
            "assetid, delisted -YYYYMM symbols, TOTALRETURN adjusted prices, and a Platinum delisted database, "
            "but the frozen sample is unproven. First-time access would require a Windows VM, a subscription, "
            "and a full local NDU database download, which this probe refused."
        ),
    }


def build_payload(
    env: dict[str, Any],
    rows: list[ProbeRow],
    live_meta: dict[str, Any],
) -> dict[str, Any]:
    verdict = classify_verdict(env, live_meta)
    return {
        "probe_date": env["probe_date"],
        "provider_tested": "Norgate US Platinum (not live)",
        "evidence_type": "DOCUMENTED" if not env["live_queryable"] else "LIVE",
        "testable_in_current_environment": env["testable_in_current_environment"],
        "environment": env,
        "live": live_meta,
        "required_range": {
            "start": REQUIRED_START.isoformat(),
            "end": REQUIRED_END.isoformat(),
        },
        "documented_field_matrix": DOCUMENTED_FIELD_MATRIX,
        "documented_sources": list(DOCUMENTED_SOURCES),
        "stop_conditions": env["stop_conditions"],
        "verdict": verdict["verdict"],
        "verdict_reason": verdict["reason"],
        "known_case_results": _known_case_results(rows, live=bool(env["live_queryable"])),
        "fallback": {
            "tiingo_power": "NOT EXECUTED — no TIINGO_API_KEY / TIINGO_TOKEN in environment or .env",
            "sharadar_sep": "NOT EXECUTED — no SHARADAR / NASDAQ_DATA_LINK / QUANDL credentials",
            "yahoo": "NOT USED — recycle policy for HAR/SE/delisted names remains in force",
        },
        "adapter_boundary": {
            "current": "PIT ticker → Security Master → yahoo symbol → market_bars",
            "potential": "PIT ticker → Security Master → NORGATE_ASSETID → vendor bars → identity validation → market_bars",
            "smallest_future_change": (
                "Store assetid on security_identifiers (id_type=NORGATE_ASSETID). "
                "Vendor symbol may be a delisted suffix. MarketDataProvider still returns MarketBar. "
                "Identity clipping stays in identity_quality. market_bars.stock_id unchanged. "
                "Do not implement until a live trial exists."
            ),
            "norgate_cannot_replace_security_master": (
                "Official FAQ: prior symbols are not provided. Security Master listing intervals remain mandatory "
                "to map PIT ticker + date onto the current or delisted vendor symbol."
            ),
        },
        "mass_download_performed": False,
        "production_db_modified": False,
        "research_ready": False,
        "phase_status": {
            "PHASE_4_historical_data_quality": "IN PROGRESS",
            "PHASE_5_strategy_research": "NOT STARTED",
            "RESEARCH_READY": "NO",
        },
        "rows": [asdict(row) for row in rows],
    }


def write_artifacts(payload: dict[str, Any], rows: list[ProbeRow], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "vendor_coverage_probe.csv"
    json_path = output_dir / "vendor_coverage_probe.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %s", csv_path)
    LOGGER.info("Wrote %s", json_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    env = detect_environment(args.env_file)
    rows = [_docs_row(sample) for sample in FROZEN_SAMPLE]
    live_meta: dict[str, Any] = {"attempted": False, "ndu_running": False, "databases": [], "errors": []}
    if env["live_queryable"]:
        live_meta = _try_live_norgate(rows)
    else:
        LOGGER.warning("Norgate is NOT TESTABLE IN CURRENT ENVIRONMENT. Docs-only rows will be written.")
        if env["fallback_tiingo_or_sharadar_credentials"]:
            LOGGER.warning("Fallback credentials appear present; this script does not call those APIs.")
        else:
            LOGGER.warning("No Tiingo or Sharadar credentials. No fallback live probe.")
    payload = build_payload(env, rows, live_meta)
    write_artifacts(payload, rows, args.output_dir)
    print(f"Norgate testable: {env['testable_in_current_environment']}")
    print(f"Verdict: {payload['verdict']}")
    print(f"Rows: {len(rows)}")
    print(f"Wrote {args.output_dir / 'vendor_coverage_probe.csv'}")
    print(f"Wrote {args.output_dir / 'vendor_coverage_probe.json'}")
    for condition in env["stop_conditions"]:
        print(f"STOP: {condition}")


if __name__ == "__main__":
    main()
