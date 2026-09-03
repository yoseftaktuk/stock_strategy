#!/usr/bin/env python3
"""Frozen-sample vendor coverage probe for Phase 4.

Proof of capability only. Does not download a vendor universe, does not write
PostgreSQL market_bars, does not replace data/raw CSVs, and does not modify
Security Master seeds.

If norgatedata and a running NDU are available, queries metadata and bounded
single-symbol history for each frozen-sample row: current ticker, and a frozen
SYMBOL-YYYYMM suffix when the occupancy ended. Does not call database_symbols,
does not scan US Equities Delisted, and does not write production data.
Live trial artifacts default to audit/norgate_trial/. Otherwise records
NOT TESTABLE IN CURRENT ENVIRONMENT from official Norgate documentation.
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
DELISTED_DATABASE_NAME = "US Equities Delisted"
LISTED_DATABASE_NAME = "US Equities"
TICKER_CHANGE_PAIRS: tuple[tuple[str, str], ...] = (
    ("COG", "CTRA"),
    ("SYMC", "GEN"),
    ("PKI", "RVTY"),
    ("SQ", "XYZ"),
)

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
    delisted_suffix: str | None = None


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
    identity_source: str = ""
    current_lookup_symbol: str = ""
    current_asset_id: str = ""
    current_security_name: str = ""
    current_first_date: str = ""
    current_last_date: str = ""
    current_lookup_error: str = ""
    delisted_lookup_symbol: str = ""
    delisted_asset_id: str = ""
    delisted_security_name: str = ""
    delisted_first_date: str = ""
    delisted_last_date: str = ""
    delisted_lookup_error: str = ""
    ticker_change_assetid_match: str = ""
    corporate_action_handling: str = "NOT_TESTABLE"

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
        delisted_suffix="ATVI-202310",
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
        delisted_suffix="CELG-201911",
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
        delisted_suffix="XLNX-202202",
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
        delisted_suffix="FRC-202305",
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
        delisted_suffix="SIVB-202303",
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
        delisted_suffix="CBS-201912",
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
        delisted_suffix="VIAB-201912",
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
        delisted_suffix="VIAC-202202",
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
        delisted_suffix="LLL-201907",
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
        delisted_suffix="RTN-202004",
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
        delisted_suffix="DWDP-201906",
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
        delisted_suffix="COG-202110",
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
        delisted_suffix="SYMC-201911",
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
        delisted_suffix="PKI-202305",
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
        delisted_suffix="DO-201610",
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
        delisted_suffix="CHK-201803",
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
        delisted_suffix="CA-201811",
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
        delisted_suffix="ADS-202006",
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
        delisted_suffix="SE-201702",
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
        delisted_suffix="HAR-201703",
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
        delisted_suffix="ESRX-201812",
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
        delisted_suffix="SQ-202501",
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
        delisted_suffix="WWE-202309",
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
        default=Path("audit/norgate_trial"),
        help=(
            "Directory for vendor_coverage_probe.csv and vendor_coverage_probe.json. "
            "Defaults to audit/norgate_trial. Refuses audit/ so the 2026-09-02 probe is not overwritten."
        ),
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


def assert_trial_output_dir(output_dir: Path) -> Path:
    """Refuse live writes that would replace audit/vendor_coverage_probe.csv."""
    resolved = output_dir.expanduser().resolve()
    forbidden = (Path.cwd() / "audit").resolve()
    if resolved == forbidden:
        raise SystemExit(
            "Refusing --output-dir audit because that would overwrite "
            "audit/vendor_coverage_probe.csv. Use audit/norgate_trial."
        )
    return output_dir


def _parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _iso_date(value: Any) -> str:
    if value is None:
        return ""
    return str(value)[:10]


def _series_len(data: Any) -> int:
    if data is None:
        return 0
    try:
        return int(len(data))
    except TypeError:
        return 0


def _series_differ(left: Any, right: Any) -> bool | None:
    if _series_len(left) == 0 or _series_len(right) == 0:
        return None
    equals = getattr(left, "equals", None)
    if callable(equals):
        return not bool(equals(right))
    return left != right


def empty_lookup_result(symbol: str, error: str = "") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "found": False,
        "assetid": "",
        "security_name": "",
        "exchange_name": "",
        "vendor_symbol": "",
        "first_date": "",
        "last_date": "",
        "daily_ohlcv": "UNKNOWN",
        "adjusted_close": "UNKNOWN",
        "unadjusted_close": "UNKNOWN",
        "corporate_action_handling": "NOT_TESTABLE",
        "error": error,
        "bar_count_totalreturn": 0,
        "bar_count_none": 0,
    }


def alias_tickers(must_not_alias: str) -> set[str]:
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


def is_alias_identity(identity: dict[str, Any], must_not_alias: str) -> bool:
    symbol = (identity.get("vendor_symbol") or identity.get("symbol") or "").upper()
    if "-" in symbol:
        symbol = symbol.split("-", 1)[0]
    return symbol in alias_tickers(must_not_alias)


def coverage_status_for_dates(first: str, last: str, sample: FrozenSample) -> str:
    first_d = _parse_iso_date(first)
    last_d = _parse_iso_date(last)
    if first_d is None or last_d is None:
        return "NOT_TESTABLE"
    valid_start = _parse_iso_date(sample.security_valid_from) or REQUIRED_START
    valid_end = _parse_iso_date(sample.security_valid_to) or REQUIRED_END
    eval_start = max(REQUIRED_START, valid_start)
    eval_end = min(REQUIRED_END, valid_end)
    if eval_start > eval_end:
        return "NOT_TESTABLE"
    if first_d <= eval_start and last_d >= eval_end:
        return "LIVE_PARTIAL"
    return "NOT_TESTABLE"


def lookup_one_symbol(client: Any, symbol: str) -> dict[str, Any]:
    """Single-symbol metadata + bounded prices. Never scans a vendor database."""
    result = empty_lookup_result(symbol)
    try:
        assetid = client.assetid(symbol)
    except Exception as exc:  # noqa: BLE001 — missing tickers are expected
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    if assetid is None:
        result["error"] = "assetid returned None"
        return result
    result["found"] = True
    result["assetid"] = str(assetid)
    try:
        name = client.security_name(symbol)
        result["security_name"] = "" if name is None else str(name)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    try:
        exchange = client.exchange_name(symbol)
        result["exchange_name"] = "" if exchange is None else str(exchange)
    except Exception:  # noqa: BLE001
        result["exchange_name"] = ""
    try:
        vendor_symbol = client.symbol(assetid)
        result["vendor_symbol"] = str(vendor_symbol if vendor_symbol is not None else symbol)
    except Exception:  # noqa: BLE001
        result["vendor_symbol"] = symbol
    try:
        result["first_date"] = _iso_date(client.first_quoted_date(symbol))
        result["last_date"] = _iso_date(client.last_quoted_date(symbol))
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    totalreturn = _bounded_price_timeseries(client, symbol, "TOTALRETURN")
    none_bars = _bounded_price_timeseries(client, symbol, "NONE")
    result["bar_count_totalreturn"] = _series_len(totalreturn)
    result["bar_count_none"] = _series_len(none_bars)
    if result["bar_count_totalreturn"]:
        result["daily_ohlcv"] = "YES"
        result["adjusted_close"] = "YES"
    differ = _series_differ(totalreturn, none_bars)
    if differ is None:
        result["corporate_action_handling"] = "NOT_TESTABLE"
    else:
        result["corporate_action_handling"] = "LIVE_PARTIAL"
        result["unadjusted_close"] = "YES" if result["bar_count_none"] else "UNKNOWN"
    return result


def _bounded_price_timeseries(client: Any, symbol: str, adjustment: str) -> Any:
    adjustment_type = getattr(client, "StockPriceAdjustmentType", None)
    setting = adjustment
    if adjustment_type is not None:
        setting = getattr(adjustment_type, adjustment, adjustment)
    kwargs: dict[str, Any] = {
        "stock_price_adjustment_setting": setting,
        "start_date": REQUIRED_START.isoformat(),
        "end_date": REQUIRED_END.isoformat(),
        "limit": 3,
        "timeseriesformat": "pandas-dataframe",
    }
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


def store_current_lookup(row: ProbeRow, result: dict[str, Any]) -> None:
    row.current_lookup_symbol = result["symbol"]
    row.current_asset_id = result["assetid"]
    row.current_security_name = result["security_name"]
    row.current_first_date = result["first_date"]
    row.current_last_date = result["last_date"]
    row.current_lookup_error = result["error"]


def store_delisted_lookup(row: ProbeRow, result: dict[str, Any]) -> None:
    row.delisted_lookup_symbol = result["symbol"]
    row.delisted_asset_id = result["assetid"]
    row.delisted_security_name = result["security_name"]
    row.delisted_first_date = result["first_date"]
    row.delisted_last_date = result["last_date"]
    row.delisted_lookup_error = result["error"]


def _format_lookup(label: str, result: dict[str, Any]) -> str:
    if result["found"]:
        return (
            f"{label} {result['symbol']}: assetid={result['assetid']} "
            f"name={result['security_name']!r} first={result['first_date']} last={result['last_date']}"
        )
    error = result["error"] or "not found"
    return f"{label} {result['symbol']}: NOT_FOUND ({error})"


def identity_lookup(
    sample: FrozenSample,
    current: dict[str, Any],
    suffix: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if sample.delisted_suffix:
        if suffix.get("found"):
            return suffix, "delisted_suffix"
        return None, ""
    if current.get("found"):
        return current, "current_ticker"
    return None, ""


def classify_live_row(
    row: ProbeRow,
    sample: FrozenSample,
    current: dict[str, Any],
    suffix: dict[str, Any],
) -> None:
    parts = [_format_lookup("Current ticker", current)]
    if sample.delisted_suffix:
        parts.append(_format_lookup("Delisted suffix", suffix))
    else:
        parts.append("Delisted suffix: not applicable (still-listed / current occupant / PIT-exit).")

    identity, source = identity_lookup(sample, current, suffix)
    row.identity_source = source
    row.evidence_type = "LIVE"
    row.ticker_history = "NO"
    alias_hit = False
    if identity is not None:
        row.vendor_security_id = identity["assetid"]
        row.vendor_symbol = identity["vendor_symbol"] or identity["symbol"]
        row.first_date = identity["first_date"]
        row.last_date = identity["last_date"]
        row.live_security_name = identity["security_name"]
        row.daily_ohlcv = identity["daily_ohlcv"]
        row.adjusted_close = identity["adjusted_close"]
        row.corporate_action_handling = identity["corporate_action_handling"]
        row.delisted_support = "YES" if source == "delisted_suffix" else "UNKNOWN"
        alias_hit = is_alias_identity(identity, sample.must_not_alias)
        row.identity_status = "FAIL" if alias_hit else "LIVE_PARTIAL"
        row.coverage_status = coverage_status_for_dates(row.first_date, row.last_date, sample)
    else:
        row.identity_status = "NOT_TESTABLE"
        row.coverage_status = "NOT_TESTABLE"
        if sample.delisted_suffix:
            row.delisted_support = "NOT_TESTABLE"
            if current.get("found"):
                parts.append(
                    "Current ticker resolved but is not historical identity for this occupancy; "
                    "suffix miss keeps identity NOT_TESTABLE."
                )
            row.live_error = suffix.get("error") or current.get("error") or ""
        else:
            row.live_error = current.get("error") or ""

    extra = ""
    if alias_hit:
        extra += " FAIL: resolved identity matches must-not-alias."
    extra += (
        " Lookup success is not PASS. Missing Trial history is not FAIL. "
        "Coverage stays NOT_TESTABLE unless quoted dates cover eval window 2013-07-08→2025-12-31."
    )
    row.notes = (
        f"{' '.join(parts)} Expected identity: {sample.expected_identity}.{extra} {sample.notes_hint}"
    ).strip()


def lookup_asset_ids(row: ProbeRow) -> set[str]:
    ids: set[str] = set()
    if row.current_asset_id:
        ids.add(row.current_asset_id)
    if row.delisted_asset_id:
        ids.add(row.delisted_asset_id)
    return ids


def compare_ticker_change_pairs(rows: list[ProbeRow]) -> dict[str, str]:
    by_ticker: dict[str, ProbeRow] = {}
    for row in rows:
        if row.ticker not in {"SE", "HAR"}:
            by_ticker[row.ticker] = row
    matches: dict[str, str] = {}
    for predecessor, successor in TICKER_CHANGE_PAIRS:
        pred = by_ticker.get(predecessor)
        succ = by_ticker.get(successor)
        if pred is None or succ is None:
            matches[f"{predecessor}->{successor}"] = "NOT_TESTABLE"
            continue
        pred_ids = lookup_asset_ids(pred)
        succ_ids = lookup_asset_ids(succ)
        if not pred_ids or not succ_ids:
            status = "NOT_TESTABLE"
        elif pred_ids & succ_ids:
            status = "YES"
        else:
            status = "NO"
        pred.ticker_change_assetid_match = status
        succ.ticker_change_assetid_match = status
        pred.notes = f"{pred.notes} Ticker-change {predecessor}->{successor} same assetid: {status}."
        succ.notes = f"{succ.notes} Ticker-change {predecessor}->{successor} same assetid: {status}."
        matches[f"{predecessor}->{successor}"] = status
    return matches


def apply_recycle_identity_rules(rows: list[ProbeRow]) -> None:
    se_2015 = next(r for r in rows if r.ticker == "SE" and "2015" in r.historical_period)
    se_2018 = next(r for r in rows if r.ticker == "SE" and "2018" in r.historical_period)
    spectra_id = se_2015.delisted_asset_id
    sea_id = se_2018.current_asset_id
    if spectra_id and sea_id:
        if spectra_id == sea_id:
            se_2015.identity_status = "FAIL"
            se_2015.notes = (
                f"{se_2015.notes} FAIL: Spectra suffix and Sea current ticker share assetid {spectra_id} "
                "(recycle collapse)."
            )
        else:
            se_2015.notes = (
                f"{se_2015.notes} Recycle-safe: Spectra assetid {spectra_id} != Sea assetid {sea_id}."
            )
            se_2018.notes = (
                f"{se_2018.notes} Recycle-safe: Sea assetid {sea_id} != Spectra assetid {spectra_id}."
            )

    har_harman = next(r for r in rows if r.ticker == "HAR" and "Harman" in r.historical_period)
    har_current = next(r for r in rows if r.ticker == "HAR" and "current" in r.historical_period)
    harman_id = har_harman.delisted_asset_id
    current_id = har_current.current_asset_id
    if harman_id and current_id:
        if harman_id == current_id:
            har_harman.identity_status = "FAIL"
            har_harman.notes = (
                f"{har_harman.notes} FAIL: Harman suffix and current HAR share assetid {harman_id} "
                "(recycle collapse)."
            )
        else:
            har_harman.notes = (
                f"{har_harman.notes} Recycle-safe: Harman assetid {harman_id} != current HAR assetid {current_id}."
            )


def apply_live_sample_lookups(
    client: Any,
    rows: list[ProbeRow],
    *,
    delisted_db_present: bool,
) -> dict[str, Any]:
    """Query the frozen 37-row sample only. Does not invoke database_symbols."""
    samples_by_ticker_period = {(row.ticker, row.historical_period): row for row in rows}
    for sample in FROZEN_SAMPLE:
        row = samples_by_ticker_period[(sample.ticker, sample.historical_period)]
        current = lookup_one_symbol(client, sample.lookup_ticker or sample.ticker)
        store_current_lookup(row, current)
        if sample.delisted_suffix:
            if delisted_db_present:
                suffix = lookup_one_symbol(client, sample.delisted_suffix)
            else:
                suffix = empty_lookup_result(
                    sample.delisted_suffix,
                    "US Equities Delisted not present; suffix lookup skipped.",
                )
            store_delisted_lookup(row, suffix)
        else:
            suffix = empty_lookup_result("")
        classify_live_row(row, sample, current, suffix)
    ticker_change = compare_ticker_change_pairs(rows)
    apply_recycle_identity_rules(rows)
    return {
        "suffix_lookups_enabled": delisted_db_present,
        "database_symbols_called": False,
        "ticker_change_assetid_match": ticker_change,
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


def _database_names(raw: list[Any]) -> list[str]:
    return [str(item) for item in raw]


def _has_database(names: list[str], expected: str) -> bool:
    return any(name.casefold() == expected.casefold() for name in names)


def _try_live_norgate(rows: list[ProbeRow]) -> dict[str, Any]:
    """Query individual symbols only. Never download a database of prices."""
    live_meta: dict[str, Any] = {
        "attempted": True,
        "ndu_running": False,
        "databases": [],
        "errors": [],
        "delisted_db_present": False,
        "suffix_lookups_enabled": False,
        "database_symbols_called": False,
        "ticker_change_assetid_match": {},
    }
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
    names: list[str] = []
    if callable(databases_fn):
        try:
            names = _database_names(list(databases_fn()))
            live_meta["databases"] = names
        except Exception as exc:  # noqa: BLE001
            live_meta["errors"].append(f"databases() failed: {exc}")

    listed_present = _has_database(names, LISTED_DATABASE_NAME)
    delisted_present = _has_database(names, DELISTED_DATABASE_NAME)
    live_meta["delisted_db_present"] = delisted_present
    if not listed_present or not delisted_present:
        live_meta["errors"].append(
            "databases() missing US Equities and/or US Equities Delisted; "
            "suffix lookups skipped (not Platinum)."
        )

    lookup_meta = apply_live_sample_lookups(
        norgatedata,
        rows,
        delisted_db_present=delisted_present,
    )
    live_meta.update(lookup_meta)
    return live_meta


def _row_by_ticker(rows: list[ProbeRow], ticker: str) -> ProbeRow:
    matches = [row for row in rows if row.ticker == ticker]
    if len(matches) != 1:
        raise KeyError(f"expected one row for {ticker}, got {len(matches)}")
    return matches[0]


def _live_observation(row: ProbeRow) -> str:
    current = (
        f"current {row.current_lookup_symbol or row.ticker} "
        f"assetid={row.current_asset_id or 'NOT_FOUND'}"
    )
    suffix = ""
    if row.delisted_lookup_symbol:
        suffix = (
            f"; suffix {row.delisted_lookup_symbol} "
            f"assetid={row.delisted_asset_id or 'NOT_FOUND'}"
        )
    return (
        f"{current}{suffix}; identity={row.identity_status} "
        f"coverage={row.coverage_status} source={row.identity_source or 'none'}"
    )


def _known_case_results(rows: list[ProbeRow], live: bool) -> dict[str, Any]:
    se_2015 = next(r for r in rows if r.ticker == "SE" and "2015" in r.historical_period)
    se_2018 = next(r for r in rows if r.ticker == "SE" and "2018" in r.historical_period)
    har_harman = next(r for r in rows if r.ticker == "HAR" and "Harman" in r.historical_period)
    har_current = next(r for r in rows if r.ticker == "HAR" and "current" in r.historical_period)
    atvi = _row_by_ticker(rows, "ATVI")
    xyz = _row_by_ticker(rows, "XYZ")
    gme = _row_by_ticker(rows, "GME")
    tko = _row_by_ticker(rows, "TKO")
    results = {
        "SE": {
            "status": "NOT_TESTABLE" if not live else se_2015.identity_status,
            "expected": "SE+2015 → Spectra Energy (assetid A); SE+2018 → Sea Limited (assetid B). FAIL if one ID or current-ticker-only.",
            "observed": (
                "Not live-tested. Documented class: delisted suffix plus distinct assetid can represent two occupancies. "
                "Official FAQ does not expose prior-symbol history, so ticker SE today would be the current occupant unless the delisted suffix is known."
                if not live
                else f"{_live_observation(se_2015)} | {_live_observation(se_2018)}"
            ),
            "spectra_row": se_2015.identity_status,
            "sea_row": se_2018.identity_status,
        },
        "HAR": {
            "status": "NOT_TESTABLE" if not live else har_harman.identity_status,
            "expected": "Harman International distinct from current HAR; bars during 2006–2017 belonging to Harman.",
            "observed": (
                "Not live-tested. Local HAR.csv remains an identity mismatch. Vendor capability class includes delisted HAR-YYYYMM, unproven for this name."
                if not live
                else f"{_live_observation(har_harman)} | {_live_observation(har_current)}"
            ),
            "harman_row": har_harman.identity_status,
            "current_row": har_current.identity_status,
        },
        "ESRX": {
            "status": "NOT_TESTABLE" if not live else _row_by_ticker(rows, "ESRX").identity_status,
            "expected": "Express Scripts own security through ~2018-12; ESRX ≠ CI.",
            "observed": "Not live-tested." if not live else _live_observation(_row_by_ticker(rows, "ESRX")),
        },
        "ATVI": {
            "status": "NOT_TESTABLE" if not live else atvi.identity_status,
            "expected": "Activision bars, not MSFT.",
            "observed": "Not live-tested." if not live else _live_observation(atvi),
        },
        "CELG": {
            "status": "NOT_TESTABLE" if not live else _row_by_ticker(rows, "CELG").identity_status,
            "expected": "Celgene bars, not BMY.",
            "observed": "Not live-tested." if not live else _live_observation(_row_by_ticker(rows, "CELG")),
        },
        "XLNX": {
            "status": "NOT_TESTABLE" if not live else _row_by_ticker(rows, "XLNX").identity_status,
            "expected": "Xilinx bars, not AMD.",
            "observed": "Not live-tested." if not live else _live_observation(_row_by_ticker(rows, "XLNX")),
        },
        "FRC": {
            "status": "NOT_TESTABLE" if not live else _row_by_ticker(rows, "FRC").identity_status,
            "expected": "First Republic own delisted series.",
            "observed": "Not live-tested." if not live else _live_observation(_row_by_ticker(rows, "FRC")),
        },
        "SIVB": {
            "status": "NOT_TESTABLE" if not live else _row_by_ticker(rows, "SIVB").identity_status,
            "expected": "SVB Financial own delisted series.",
            "observed": "Not live-tested." if not live else _live_observation(_row_by_ticker(rows, "SIVB")),
        },
        "TKO": {
            "status": "NOT_TESTABLE" if not live else tko.identity_status,
            "expected": "TKO from 2023-09-12 as a new issuer; WWE predecessor bars must not be labeled TKO.",
            "observed": (
                "Not live-tested. Residual risk already documented: Norgate surviving-entity / merger-of-equals rules may prepend WWE history under TKO."
                if not live
                else _live_observation(tko)
            ),
        },
        "XYZ": {
            "status": "NOT_TESTABLE" if not live else xyz.identity_status,
            "expected": "Same assetid across SQ→XYZ (same Class A).",
            "observed": (
                "Not live-tested. Documented behavior prepends history onto the current symbol and keeps one assetid through ticker changes."
                if not live
                else f"{_live_observation(_row_by_ticker(rows, 'SQ'))} | {_live_observation(xyz)}; pair={xyz.ticker_change_assetid_match or 'NOT_TESTABLE'}"
            ),
        },
        "GME": {
            "status": "NOT_TESTABLE" if not live else gme.identity_status,
            "expected": "One stable identity and ordinary daily history.",
            "observed": "Not live-tested. Control case remains unproven on Norgate until NDU is available."
            if not live
            else _live_observation(gme),
        },
    }
    return results


def classify_verdict(env: dict[str, Any], live_meta: dict[str, Any]) -> dict[str, str]:
    if env["live_queryable"] and live_meta.get("ndu_running"):
        return {
            "verdict": "INSUFFICIENT",
            "reason": (
                "Live NDU was reachable and the 37-row sample was queried "
                "(current ticker plus frozen SYMBOL-YYYYMM). Trial coverage cannot prove "
                "2013-07-08→2025-12-31, so rows stay NOT_TESTABLE or LIVE_PARTIAL; "
                "vendor-class remains INSUFFICIENT / PARTIALLY SUITABLE."
            ),
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
        "provider_tested": (
            "Norgate US Platinum" if env["live_queryable"] else "Norgate US Platinum (not live)"
        ),
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
    assert_trial_output_dir(output_dir)
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
    assert_trial_output_dir(args.output_dir)
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
