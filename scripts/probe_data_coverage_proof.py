#!/usr/bin/env python3
"""Round 13 read-only Data Access & Coverage Proof.

Isolated from production. Does not ingest, migrate, or replace Yahoo.
Does not import BacktestEngine, Broker, accounting, or market_bars writers.

Writes only under audit/data_coverage_proof/.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.security_master.identity_resolver import CatalogIdentityResolver, catalog_security_id
from app.security_master.seed import load_known_identities_catalog
from app.security_master.vendor import preferred_vendor_symbol, vendor_fetch_symbols
from app.universe.memory import InMemoryUniverseProvider
from app.universe.providers.sp500 import DEFAULT_CACHE_PATH, SP500HistoricalSource

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

RESEARCH_START = date(2013, 7, 8)
RESEARCH_END = date(2025, 12, 31)
EVAL_START = date(2015, 1, 1)
EVAL_END = date(2025, 12, 31)

CSV_DIR = _ROOT / "data" / "raw"
COVERAGE_PATH = _ROOT / "audit" / "market_data_coverage" / "coverage.json"
TRIAL_PROBE_PATH = _ROOT / "audit" / "norgate_trial" / "vendor_coverage_probe.json"
OUTPUT_DIR = _ROOT / "audit" / "data_coverage_proof"

PIT_SAMPLES = (
    ("AAPL", date(2015, 1, 2), "current_constituent"),
    ("MSFT", date(2020, 6, 15), "current_constituent"),
    ("ATVI", date(2018, 6, 1), "historical_then_acquired"),
    ("ESRX", date(2016, 6, 1), "historical_then_acquired"),
    ("SE", date(2015, 6, 1), "historical_constituent_spectra"),
    ("SE", date(2020, 6, 1), "later_recycled_ticker_sea"),
    ("HAR", date(2016, 6, 1), "historical_then_acquired"),
    ("BRK.B", date(2015, 1, 2), "share_class"),
    ("BF.B", date(2015, 1, 2), "share_class"),
    ("CELG", date(2018, 6, 1), "historical_then_acquired"),
    ("XYZ", date(2025, 8, 1), "ticker_changed_current"),
)


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


def _csv_bounds(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "first_date": None, "last_date": None, "sessions": 0}
    first: str | None = None
    last: str | None = None
    sessions = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stamp = (row.get("Date") or row.get("date") or "").strip()
            if not stamp:
                continue
            sessions += 1
            if first is None:
                first = stamp[:10]
            last = stamp[:10]
    return {"exists": True, "first_date": first, "last_date": last, "sessions": sessions}


def detect_environment() -> dict[str, Any]:
    vm_apps = {name: bundle.is_dir() for name, bundle in VM_APP_BUNDLES}
    vm_clis = {name: bool(shutil.which(name)) for name in VM_CLIS}
    norgatedata_importable = False
    norgatedata_error = ""
    ndu_running: bool | None = None
    databases: list[str] = []
    try:
        import norgatedata  # type: ignore[import-not-found]

        norgatedata_importable = True
        status_fn = getattr(norgatedata, "status", None)
        if callable(status_fn):
            ndu_running = bool(status_fn())
        databases_fn = getattr(norgatedata, "databases", None)
        if callable(databases_fn) and ndu_running:
            databases = [str(item) for item in databases_fn()]
    except Exception as exc:  # noqa: BLE001
        norgatedata_error = f"{type(exc).__name__}: {exc}"

    env_file = _ROOT / ".env"
    env_keys = _env_file_keys(env_file)
    credential_env = {key: bool(os.environ.get(key)) for key in VENDOR_CREDENTIAL_KEYS}
    credential_file = {key: key in env_keys for key in VENDOR_CREDENTIAL_KEYS}
    sharadar_keys = ("SHARADAR_API_KEY", "NASDAQ_DATA_LINK_API_KEY", "QUANDL_API_KEY")
    sharadar_present = any(credential_env[k] or credential_file[k] for k in sharadar_keys)

    windows_vm_available = any(vm_apps.values()) or any(vm_clis.values())
    ndu_paths = [
        Path("/Applications/Norgate Data Updater.app"),
        Path.home() / "NorgateData",
        Path("/Program Files/Norgate Data"),
        Path("/mnt/c/Program Files/Norgate Data"),
    ]
    ndu_installed = any(path.exists() for path in ndu_paths)
    live_queryable = bool(norgatedata_importable and ndu_running)

    nasdaq_importable = False
    nasdaq_error = ""
    try:
        import nasdaqdatalink  # type: ignore[import-not-found]

        nasdaq_importable = True
        del nasdaqdatalink
    except Exception as exc:  # noqa: BLE001
        nasdaq_error = f"{type(exc).__name__}: {exc}"

    if live_queryable:
        norgate_access = "LIVE_OPERATIONAL"
    elif not norgatedata_importable or not windows_vm_available or platform.system() != "Windows":
        norgate_access = "ACCESS_BLOCKED"
    else:
        norgate_access = "NOT_AVAILABLE"

    if sharadar_present and nasdaq_importable:
        sharadar_access = "LIVE_OPERATIONAL"
    elif not sharadar_present:
        sharadar_access = "NOT_AVAILABLE"
    else:
        sharadar_access = "ACCESS_BLOCKED"

    return {
        "probe_date": date.today().isoformat(),
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "norgatedata_importable": norgatedata_importable,
        "norgatedata_error": norgatedata_error,
        "ndu_running": ndu_running,
        "ndu_installed": ndu_installed,
        "ndu_path_hits": [str(path) for path in ndu_paths if path.exists()],
        "databases": databases,
        "windows_host": platform.system() == "Windows",
        "windows_vm_available": windows_vm_available,
        "vm_apps": vm_apps,
        "vm_clis": vm_clis,
        "credential_env_present": credential_env,
        "credential_env_file_present": credential_file,
        "env_file_exists": env_file.is_file(),
        "sharadar_credentials_present": sharadar_present,
        "nasdaqdatalink_importable": nasdaq_importable,
        "nasdaqdatalink_error": nasdaq_error,
        "live_norgate_queryable": live_queryable,
        "norgate_platinum_access": norgate_access,
        "sharadar_actions_access": sharadar_access,
        "platinum_entitlement_proven": False,
        "notes": [
            "Platinum entitlement is not proven from Trial artifacts.",
            "Trial live evidence (Windows 11 ARM64, 2026-09-03) is not this environment.",
            "No Sharadar / Nasdaq Data Link / Quandl credentials in env or .env.",
        ],
    }


def _ref_payload(ref: Any) -> dict[str, Any]:
    listing = ref.listing
    return {
        "resolved": bool(ref.is_resolved),
        "security_id": ref.security_id,
        "ticker_as_of": ref.ticker_as_of,
        "listing_id": None if listing is None else listing.listing_id,
        "listing_ticker": None if listing is None else listing.ticker,
        "valid_from": None if listing is None else listing.valid_from.isoformat(),
        "valid_to": None
        if listing is None or listing.valid_to is None
        else listing.valid_to.isoformat(),
        "position_key": str(ref.position_key()),
    }


def prove_identity_cases(coverage_by_ticker: dict[str, dict[str, Any]]) -> dict[str, Any]:
    master = load_known_identities_catalog()
    resolver = CatalogIdentityResolver.from_catalog(master)
    window = (RESEARCH_START, RESEARCH_END)

    sq = resolver.resolve("SQ", date(2024, 6, 3))
    xyz = resolver.resolve("XYZ", date(2025, 6, 2))
    spectra = resolver.resolve("SE", date(2015, 6, 1))
    sea = resolver.resolve("SE", date(2018, 6, 1))
    gap = resolver.resolve("SE", date(2017, 6, 1))
    esrx = resolver.resolve("ESRX", date(2018, 6, 1))
    esrx_after = resolver.resolve("ESRX", date(2019, 1, 2))
    ci = resolver.resolve("CI", date(2018, 6, 1))
    atvi = resolver.resolve("ATVI", date(2018, 6, 1))
    msft = resolver.resolve("MSFT", date(2023, 10, 1))
    brk_b = resolver.resolve("BRK.B", date(2015, 6, 1))
    bf_b = resolver.resolve("BF.B", date(2015, 6, 1))
    brk_a = resolver.resolve("BRK.A", date(2015, 6, 1))
    bf_a = resolver.resolve("BF.A", date(2015, 6, 1))
    har_hist = resolver.resolve("HAR", date(2016, 6, 1))
    har_now = resolver.resolve("HAR", date(2020, 6, 1))
    celg = resolver.resolve("CELG", date(2018, 6, 1))

    xyz_csv = _csv_bounds(CSV_DIR / "XYZ.csv")
    sq_csv = _csv_bounds(CSV_DIR / "SQ.csv")
    se_csv = _csv_bounds(CSV_DIR / "SE.csv")
    esrx_csv = _csv_bounds(CSV_DIR / "ESRX.csv")
    ci_csv = _csv_bounds(CSV_DIR / "CI.csv")
    atvi_csv = _csv_bounds(CSV_DIR / "ATVI.csv")
    brk_csv = _csv_bounds(CSV_DIR / "BRK-B.csv")
    bf_csv = _csv_bounds(CSV_DIR / "BF-B.csv")
    har_csv = _csv_bounds(CSV_DIR / "HAR.csv")
    aapl_csv = _csv_bounds(CSV_DIR / "AAPL.csv")
    msft_csv = _csv_bounds(CSV_DIR / "MSFT.csv")

    cases = {
        "case_1_sq_xyz": {
            "expected": "same economic security",
            "internal_security_ids": {
                "SQ_2024": _ref_payload(sq),
                "XYZ_2025": _ref_payload(xyz),
            },
            "same_security_id": sq.is_resolved
            and xyz.is_resolved
            and sq.security_id == xyz.security_id
            == catalog_security_id("block-inc-class-a"),
            "same_position_key": sq.position_key() == xyz.position_key(),
            "distinct_listings": sq.listing is not None
            and xyz.listing is not None
            and sq.listing.listing_id != xyz.listing.listing_id,
            "vendor_fetch_symbols": vendor_fetch_symbols(master, "SQ", *window)
            + vendor_fetch_symbols(master, "XYZ", *window),
            "yahoo_csv": {"SQ": sq_csv, "XYZ": xyz_csv},
            "yahoo_coverage_row": coverage_by_ticker.get("XYZ"),
            "norgate_trial_2026_09_03": "XYZ assetid=2104402 LIVE_PARTIAL; SQ NOT_FOUND (prepend). Not Platinum.",
            "norgate_platinum_live": "BLOCKED",
            "sharadar_permaticker_live": "NOT_AVAILABLE",
            "vendor_id_relationship": "UNKNOWN",
            "status": "PARTIAL",
            "notes": (
                "Internal Security Master maps SQ occupancy and XYZ occupancy to the same "
                "security_id without ticker guessing. Vendor assetid/permaticker continuity "
                "is not live-proven on Platinum or Sharadar."
            ),
        },
        "case_2_spectra_se_vs_sea": {
            "expected": "different securities; ticker equality must not alias",
            "internal_security_ids": {
                "SE_2015_spectra": _ref_payload(spectra),
                "SE_2018_sea": _ref_payload(sea),
                "SE_2017_gap": _ref_payload(gap),
            },
            "different_security_id": spectra.is_resolved
            and sea.is_resolved
            and spectra.security_id != sea.security_id,
            "gap_unresolved": gap.is_resolved is False,
            "yahoo_csv": se_csv,
            "yahoo_coverage_row": coverage_by_ticker.get("SE"),
            "yahoo_aliasing": "Yahoo SE.csv is Sea from 2017-10-20, not Spectra.",
            "norgate_trial_2026_09_03": "Sea SE assetid=2326776 LIVE_PARTIAL; SE-201702 Spectra NOT_FOUND.",
            "norgate_platinum_live": "BLOCKED",
            "status": "PARTIAL",
            "notes": (
                "Internal occupancy prevents aliasing. Spectra historical prices are missing "
                "on Yahoo and were NOT_FOUND on Norgate Trial. Platinum presence is unproven."
            ),
        },
        "case_3_esrx_ci": {
            "expected": "predecessor remains distinct; do not map ESRX to CI",
            "internal_security_ids": {
                "ESRX_2018": _ref_payload(esrx),
                "ESRX_after_listing": _ref_payload(esrx_after),
                "CI_2018": _ref_payload(ci),
            },
            "esrx_resolved": esrx.is_resolved
            and esrx.security_id == catalog_security_id("express-scripts"),
            "ci_not_aliased": ci.is_resolved is False,
            "esrx_after_unresolved": esrx_after.is_resolved is False,
            "catalog_status": None
            if master.get_security("express-scripts") is None
            else master.get_security("express-scripts").status,
            "yahoo_csv": {"ESRX": esrx_csv, "CI": ci_csv},
            "yahoo_coverage_row": coverage_by_ticker.get("ESRX"),
            "norgate_trial_2026_09_03": "ESRX and ESRX-201812 NOT_FOUND.",
            "norgate_platinum_live": "BLOCKED",
            "merger_terms": "UNRESOLVED",
            "status": "PARTIAL",
            "notes": (
                "Internal identity keeps ESRX distinct from CI. Local ESRX.csv covers "
                "2013-07-08 through 2018-12-21 (coverage audit). Cigna is not seeded. "
                "Acquisition economics are not available from any connected source."
            ),
        },
        "case_4_atvi": {
            "expected": "acquired/delisted Activision remains its own security",
            "internal_security_ids": {
                "ATVI_2018": _ref_payload(atvi),
                "MSFT_2023": _ref_payload(msft),
            },
            "atvi_seeded": master.get_security("activision") is not None,
            "atvi_unresolved": atvi.is_resolved is False,
            "msft_not_seeded": msft.is_resolved is False,
            "yahoo_csv": atvi_csv,
            "yahoo_coverage_row": coverage_by_ticker.get("ATVI"),
            "norgate_trial_2026_09_03": "ATVI and ATVI-202310 NOT_FOUND.",
            "norgate_platinum_live": "BLOCKED",
            "corporate_actions_live": "NOT_AVAILABLE",
            "merger_terms": "UNRESOLVED",
            "status": "FAIL",
            "notes": (
                "ATVI is not in the known-identities catalog. No local CSV. Trial suffix "
                "lookup failed. Merger cash/share terms cannot be invented."
            ),
        },
        "case_5_share_classes": {
            "expected": "BRK.B and BF.B uniquely identified",
            "internal_security_ids": {
                "BRK.B": _ref_payload(brk_b),
                "BF.B": _ref_payload(bf_b),
                "BRK.A": _ref_payload(brk_a),
                "BF.A": _ref_payload(bf_a),
            },
            "class_b_distinct": brk_b.is_resolved
            and bf_b.is_resolved
            and brk_b.security_id != bf_b.security_id,
            "class_a_unseeded": brk_a.is_resolved is False and bf_a.is_resolved is False,
            "yahoo_symbols": {
                "BRK.B": vendor_fetch_symbols(master, "BRK.B", *window),
                "BF.B": vendor_fetch_symbols(master, "BF.B", *window),
                "preferred_BRK.B": preferred_vendor_symbol(master, "BRK.B", *window),
                "preferred_BF.B": preferred_vendor_symbol(master, "BF.B", *window),
            },
            "yahoo_csv": {"BRK-B": brk_csv, "BF-B": bf_csv},
            "norgate_assetid_live": "UNKNOWN",
            "sharadar_permaticker_live": "UNKNOWN",
            "status": "PARTIAL",
            "notes": (
                "Internal catalog distinguishes Class B listings and Yahoo hyphen symbols. "
                "Vendor IDs (Norgate assetid / Sharadar permaticker) and Class A uniqueness "
                "are not live-proven."
            ),
        },
        "case_6_ticker_recycle": {
            "expected": "two occupancy periods do not collapse into one canonical security",
            "primary_example": "SE Spectra vs Sea (case 2)",
            "secondary_example": "HAR Harman vs later namesake",
            "harman": _ref_payload(har_hist),
            "har_after": _ref_payload(har_now),
            "harman_resolved": har_hist.is_resolved
            and har_hist.security_id == catalog_security_id("harman-international"),
            "later_har_unresolved": har_now.is_resolved is False,
            "yahoo_csv": har_csv,
            "yahoo_coverage_row": coverage_by_ticker.get("HAR"),
            "norgate_trial_2026_09_03": "HAR and HAR-201703 NOT_FOUND.",
            "status": "PARTIAL",
            "notes": (
                "SE occupancies are distinct internally. HAR occupancy after 2017-03-13 does "
                "not resolve to Harman. Local HAR.csv is identity_mismatch (not Harman). "
                "Vendor recycle-safe fetch by assetid is not live-proven on Platinum."
            ),
        },
        "case_7_delisted": {
            "expected": "a security that no longer trades remains in the research universe",
            "examples": {
                "ESRX": {
                    "seed_key": "express-scripts",
                    "status": None
                    if master.get_security("express-scripts") is None
                    else master.get_security("express-scripts").status,
                    "ref": _ref_payload(esrx),
                    "yahoo_csv": esrx_csv,
                    "last_quoted_yahoo": esrx_csv.get("last_date"),
                    "delisting_proceeds": "UNKNOWN",
                    "last_close_proxy_only": True,
                },
                "ATVI": {
                    "seed_key": None,
                    "status": "UNSEEDED",
                    "ref": _ref_payload(atvi),
                    "yahoo_csv": atvi_csv,
                    "delisting_proceeds": "UNKNOWN",
                },
                "HAR": {
                    "seed_key": "harman-international",
                    "status": None
                    if master.get_security("harman-international") is None
                    else master.get_security("harman-international").status,
                    "ref": _ref_payload(har_hist),
                    "yahoo_csv": har_csv,
                    "yahoo_usable_for_harman": False,
                    "delisting_proceeds": "UNKNOWN",
                },
            },
            "norgate_delisted_class": "DOCUMENTED (US Equities Delisted). LIVE Platinum: BLOCKED. Trial pre-window NOT_FOUND.",
            "status": "PARTIAL",
            "notes": (
                "Catalog can retain DELISTED securities (ESRX, HAR). Yahoo supplies ESRX last "
                "close as a proxy only. True delisting proceeds are unavailable."
            ),
        },
    }

    listed_controls = {
        "AAPL": {**aapl_csv, "coverage": coverage_by_ticker.get("AAPL")},
        "MSFT": {**msft_csv, "coverage": coverage_by_ticker.get("MSFT")},
        "CELG": {**_csv_bounds(CSV_DIR / "CELG.csv"), "coverage": coverage_by_ticker.get("CELG"), "ref": _ref_payload(celg)},
    }
    return {"cases": cases, "listed_controls_yahoo_only": listed_controls}


def load_coverage_index() -> dict[str, dict[str, Any]]:
    if not COVERAGE_PATH.is_file():
        return {}
    payload = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    return {str(row.get("historical_ticker")): row for row in rows}


def prove_pit(coverage_by_ticker: dict[str, dict[str, Any]]) -> dict[str, Any]:
    master = load_known_identities_catalog()
    resolver = CatalogIdentityResolver.from_catalog(master)
    cache = DEFAULT_CACHE_PATH
    memberships_loaded = False
    provider: InMemoryUniverseProvider | None = None
    load_error = ""
    source_version = ""
    if cache.is_file():
        try:
            loaded = SP500HistoricalSource(cache_path=cache).load(source_file=cache)
            provider = InMemoryUniverseProvider(loaded.memberships)
            memberships_loaded = True
            source_version = loaded.source_version
        except Exception as exc:  # noqa: BLE001
            load_error = f"{type(exc).__name__}: {exc}"
    else:
        load_error = f"PIT cache missing: {cache}"

    samples: list[dict[str, Any]] = []
    for ticker, as_of, role in PIT_SAMPLES:
        members = [] if provider is None else provider.get_symbols(as_of)
        in_pit = ticker in members
        ref = resolver.resolve(ticker, as_of)
        coverage = coverage_by_ticker.get(ticker, {})
        samples.append(
            {
                "ticker": ticker,
                "as_of": as_of.isoformat(),
                "role": role,
                "pit_membership": in_pit if memberships_loaded else "UNKNOWN",
                "pit_interval": {
                    "start": coverage.get("pit_start"),
                    "end": coverage.get("pit_end"),
                },
                "internal_security_id": ref.security_id,
                "identity_resolved": bool(ref.is_resolved),
                "vendor_norgate_assetid": "BLOCKED",
                "vendor_sharadar_permaticker": "NOT_AVAILABLE",
                "historical_price_availability": coverage.get("market_data_status"),
                "yahoo_price_start": coverage.get("price_start"),
                "yahoo_price_end": coverage.get("price_end"),
            }
        )

    catalog_seed_count = len(master.securities())
    unresolved = sum(
        1 for row in coverage_by_ticker.values() if row.get("identity_status") == "UNRESOLVED"
    )
    return {
        "canonical_source": "unofficial fja05680 data/raw/sp500_historical.csv",
        "official_spdji": False,
        "memberships_loaded": memberships_loaded,
        "source_version_sha256": source_version,
        "load_error": load_error,
        "catalog_seed_count": catalog_seed_count,
        "coverage_unresolved_identity": unresolved,
        "coverage_pit_securities": len(coverage_by_ticker),
        "norgate_spx_crosscheck": "BLOCKED — not live-queried",
        "sharadar_sp500_crosscheck": "NOT_AVAILABLE — no credentials; SP500 may require bundle SKU",
        "samples": samples,
        "status": "PARTIAL" if memberships_loaded else "BLOCKED",
        "notes": (
            "PIT membership can be reconstructed from unofficial fja05680. Join to canonical "
            "security_id works only for seeded catalog names. Join to vendor identifiers is "
            "not live-proven. Current S&P 500 list was not used."
        ),
    }


def corporate_action_proof(env: dict[str, Any]) -> dict[str, Any]:
    live = env["sharadar_actions_access"]
    documented = {
        "split": {
            "documented_fields": ["date", "action=split", "ticker", "name", "value"],
            "maps_to": "CorporateAction.factor",
            "live_proven": False,
            "status": "UNKNOWN",
        },
        "reverse_split": {
            "documented_fields": ["date", "action=split", "value < 1 expected but not live-proven"],
            "maps_to": "CorporateAction.factor",
            "live_proven": False,
            "status": "UNKNOWN",
        },
        "dividend": {
            "documented_fields": ["date", "action (dividend labels)", "value as amount"],
            "maps_to": "CorporateAction.amount on ex-date",
            "ex_date_live_proven": False,
            "live_proven": False,
            "status": "UNKNOWN",
        },
        "merger": {
            "documented_fields": ["action=acquisition", "contraticker", "contraname", "value UNKNOWN semantics"],
            "cash_per_share": "UNKNOWN",
            "share_conversion_ratio": "UNKNOWN",
            "live_proven": False,
            "status": "UNRESOLVED",
        },
        "acquisition": {
            "documented_fields": ["acquisition events marketed"],
            "terms": "UNKNOWN",
            "live_proven": False,
            "status": "UNRESOLVED",
        },
        "delisting": {
            "documented_fields": ["delist reasons marketed; proceeds not in public columns"],
            "proceeds": "UNKNOWN",
            "last_quoted_close_proxy": True,
            "live_proven": False,
            "status": "PARTIAL",
        },
    }
    norgate = {
        "split_factor": "UNSUPPORTED (FAQ: no direct CA details; capital_event boolean only)",
        "dividend_amount": "PARTIAL documented (column when not TOTALRETURN; entitlement = day before ex-date). Not live-proven here.",
        "merger_terms": "UNSUPPORTED (FAQ identity rules only)",
        "delisting_proceeds": "PARTIAL (last bar; FAQ: no delisting return)",
        "live_proven_this_environment": False,
    }
    return {
        "documented_capability": "SHARADAR/ACTIONS public columns date, action, ticker, name, value, contraticker, contraname",
        "live_access": live,
        "operational_status": "UNKNOWN" if live != "LIVE_OPERATIONAL" else "LIVE_OPERATIONAL",
        "event_types": documented,
        "norgate_complement": norgate,
        "split_proof": {
            "forward_split": "NOT TESTED — no credentials",
            "reverse_split": "NOT TESTED — no credentials",
            "do_not_derive_from_adjusted_prices": True,
        },
        "dividend_proof": {
            "amount_per_share": "NOT TESTED — no credentials",
            "economic_ex_date": "NOT TESTED — no credentials",
            "security_identity": "NOT TESTED — no credentials",
        },
        "merger_proof": {
            "cash_per_share": "UNRESOLVED",
            "share_conversion_ratio": "UNRESOLVED",
            "identity_relationship": "UNKNOWN until live ACTIONS rows",
            "effective_date": "UNKNOWN",
            "prevents_research_grade_accounting": True,
            "explicit_unresolved_event_policy": (
                "Project may continue infrastructure with UNRESOLVED acquisitions; "
                "it may not invent proceeds or conversion ratios."
            ),
        },
        "delisting_proof": {
            "known_proceeds": False,
            "fallback": "last quoted close as proxy only",
            "dedicated_delisting_return": "UNAVAILABLE on Norgate (FAQ) and unproven on Sharadar",
            "delisting_proceeds": "PARTIAL",
        },
    }


def norgate_field_semantics(env: dict[str, Any]) -> dict[str, Any]:
    live = env["live_norgate_queryable"]
    fields = {
        "assetid": "DOCUMENTED integer vendor ID. Trial live for some listed names. Platinum: not live here.",
        "symbol": "DOCUMENTED current symbol only. Prior symbols not provided.",
        "date": "DOCUMENTED",
        "open": "DOCUMENTED",
        "high": "DOCUMENTED",
        "low": "DOCUMENTED",
        "close": "DOCUMENTED",
        "volume": "DOCUMENTED consolidated tape",
        "TOTALRETURN": "DOCUMENTED default price_timeseries mode. Trial used it. Platinum: not live here.",
        "CAPITAL": "DOCUMENTED split-adjusted, not ordinary-dividend-adjusted. Not live-proven here.",
    }
    roles = {
        "SIGNAL": {"required": "TOTALRETURN Close", "live_proven": False, "status": "UNKNOWN"},
        "MARK": {"required": "CAPITAL Close", "live_proven": False, "status": "UNKNOWN"},
        "EXECUTION": {"required": "next-session CAPITAL Open", "live_proven": False, "status": "UNKNOWN"},
        "TERMINAL": {"required": "CAPITAL Close", "live_proven": False, "status": "UNKNOWN"},
    }
    return {
        "live_probe_attempted": live,
        "live_probe_result": "NOT EXECUTED — norgatedata/NDU unavailable"
        if not live
        else "EXECUTED",
        "fields": fields,
        "price_roles": roles,
        "trial_is_not_platinum": True,
        "status": "BLOCKED" if not live else "LIVE_OPERATIONAL",
    }


def load_trial_known_cases() -> dict[str, Any]:
    if not TRIAL_PROBE_PATH.is_file():
        return {}
    payload = json.loads(TRIAL_PROBE_PATH.read_text(encoding="utf-8"))
    return {
        "evidence_type": payload.get("evidence_type"),
        "probe_date": payload.get("probe_date"),
        "os": payload.get("environment", {}).get("os"),
        "databases": payload.get("live", {}).get("databases"),
        "known_case_results": payload.get("known_case_results", {}),
        "verdict": payload.get("verdict"),
        "note": "Windows Trial 2026-09-03. Not this Mac. Not Platinum depth.",
    }


def classify_gates(env: dict[str, Any], identity: dict[str, Any], pit: dict[str, Any], ca: dict[str, Any]) -> dict[str, Any]:
    cases = identity["cases"]
    identity_internal_pass = all(
        [
            cases["case_1_sq_xyz"]["same_security_id"],
            cases["case_2_spectra_se_vs_sea"]["different_security_id"],
            cases["case_3_esrx_ci"]["esrx_resolved"] and cases["case_3_esrx_ci"]["ci_not_aliased"],
            cases["case_5_share_classes"]["class_b_distinct"],
            cases["case_6_ticker_recycle"]["harman_resolved"],
        ]
    )
    return {
        "gate_a_market_data": {
            "question": "Retrieve 2013-07-08 → 2025-12-31 with required price roles?",
            "result": "BLOCKED",
            "reason": "Norgate Platinum not reachable; Sharadar SEP not credentialed. Yahoo listed depth is not the selected tape.",
        },
        "gate_b_identity": {
            "question": "Security Master map vendor records without ticker guessing?",
            "result": "PARTIAL" if identity_internal_pass else "FAIL",
            "reason": (
                "Internal occupancy mapping is proven for seeded cases. Vendor record mapping "
                "(assetid/permaticker) is not live. ATVI unseeded. Catalog still exceptions-only."
            ),
        },
        "gate_c_pit": {
            "question": "Historical membership joined to canonical security identity?",
            "result": pit["status"],
            "reason": pit["notes"],
        },
        "gate_d_corporate_actions": {
            "question": "Represent split/reverse/dividend/merger/delisting without inventing economics?",
            "result": "PARTIAL",
            "reason": (
                "Domain can leave mergers UNRESOLVED. Live factor/amount rows are not available. "
                "Merger terms remain UNRESOLVED. Delisting proceeds PARTIAL (last-close proxy)."
            ),
        },
        "gate_e_survivorship": {
            "question": "Historical delisted/acquired securities remain in the research tape?",
            "result": "PARTIAL",
            "reason": (
                "Catalog retains DELISTED names. Yahoo cannot supply Spectra/ATVI/HAR Harman. "
                "Selected vendor delisted tape is not live."
            ),
        },
        "gate_f_access": {
            "question": "Can this project obtain the required data under current constraints?",
            "result": "FAIL",
            "reason": (
                f"norgate_platinum_access={env['norgate_platinum_access']}; "
                f"sharadar_actions_access={env['sharadar_actions_access']}"
            ),
        },
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = detect_environment()
    coverage = load_coverage_index()
    identity = prove_identity_cases(coverage)
    pit = prove_pit(coverage)
    ca = corporate_action_proof(env)
    fields = norgate_field_semantics(env)
    trial = load_trial_known_cases()
    gates = classify_gates(env, identity, pit, ca)

    coverage_matrix_status = {
        "2013-07-08_depth": "BLOCKED",
        "2025-12-31_depth": "BLOCKED",
        "TOTALRETURN": "UNKNOWN",
        "CAPITAL_Open": "UNKNOWN",
        "CAPITAL_Close": "UNKNOWN",
        "split_factor": "UNKNOWN",
        "dividend_amount": "UNKNOWN",
        "merger_terms": "UNRESOLVED",
        "delisting_proceeds": "PARTIAL",
        "security_identity": "PARTIAL",
        "ticker_history": "PARTIAL",
        "share_classes": "PARTIAL",
        "pit_membership": pit["status"],
        "delisted_coverage": "PARTIAL",
        "survivorship_free": "PARTIAL",
    }

    payload = {
        "round": 13,
        "assessment_date": date.today().isoformat(),
        "production_modified": False,
        "data_layer_implementation_started": False,
        "environment": env,
        "norgate_field_semantics": fields,
        "identity": identity,
        "pit": pit,
        "corporate_actions": ca,
        "norgate_trial_prior_evidence": trial,
        "gates": gates,
        "coverage_matrix_status": coverage_matrix_status,
        "final_decision": "CONDITIONAL GO",
        "decision_reason": (
            "Option C hybrid remains the target architecture, but neither Norgate Platinum "
            "nor Sharadar ACTIONS is operationally available in this environment. Mandatory "
            "price-role and CA-factor capabilities are documented, not live-proven."
        ),
    }
    out = OUTPUT_DIR / "probe.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"norgate_platinum_access={env['norgate_platinum_access']}")
    print(f"sharadar_actions_access={env['sharadar_actions_access']}")
    print(f"final_decision={payload['final_decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
