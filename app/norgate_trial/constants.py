"""Dates, databases, and identity gates for the Norgate vendor-validation trial.

Official current scope is the 2-year Trial overlap with this project's PIT
endpoint: 2024-09-03 → 2025-12-31. Full-history Platinum
(2013-07-08 → 2025-12-31) remains a future gate.
"""

from datetime import date

# Official vendor-validation window (observed Trial first_quoted ∩ PIT endpoint).
EVAL_START = date(2024, 9, 3)
EVAL_END = date(2025, 12, 31)
RESEARCH_WINDOW_START = date(2024, 9, 3)
RESEARCH_WINDOW_END = date(2025, 12, 31)
TRIAL_HISTORY_START = date(2024, 9, 3)

# Future Full Historical Research Ready gate only. Not the current GO window.
FULL_HISTORY_EVAL_START = date(2013, 7, 8)

LISTED_DATABASE_NAME = "US Equities"
DELISTED_DATABASE_NAME = "US Equities Delisted"
SPX_INDEX_NAMES: tuple[str, ...] = ("S&P 500", "$SPX")

PACKAGE_PROOF_SYMBOLS: tuple[str, ...] = ("GME", "AVB")
DELISTED_PROBE_SUFFIXES: tuple[str, ...] = (
    "ATVI-202310",
    "CELG-201911",
    "SE-201702",
    "HAR-201703",
    "ESRX-201812",
)

TICKER_CHANGE_PAIRS: tuple[tuple[str, str], ...] = (
    ("COG", "CTRA"),
    ("SYMC", "GEN"),
    ("PKI", "RVTY"),
    ("SQ", "XYZ"),
)

JOIN_AS_OF_DATES: tuple[date, ...] = (date(2024, 10, 1), date(2025, 8, 1))

# Identity-critical occupancies that may sit outside the 2-year PIT window.
# Coverage for empty occupancy ∩ eval window is NOT_TESTABLE; current-ticker
# contamination of these rows remains FAIL.
OVERLAY_OCCUPANCIES: tuple[tuple[str, date, date | None, str, str], ...] = (
    ("SE", date(2007, 1, 3), date(2017, 2, 27), "Spectra Energy Corp", "spectra-energy"),
    ("SE", date(2017, 10, 20), None, "Sea Limited", "sea-limited"),
    ("HAR", date(2006, 2, 1), date(2017, 3, 13), "Harman International Industries", "harman-international"),
    ("ATVI", date(2015, 8, 31), date(2023, 10, 18), "Activision Blizzard", "atvi-activision"),
    ("CELG", date(2006, 11, 6), date(2019, 11, 21), "Celgene", "celg-celgene"),
    ("XLNX", date(1999, 11, 8), date(2022, 2, 15), "Xilinx", "xlnx-xilinx"),
    ("FRC", date(2019, 1, 2), date(2023, 5, 4), "First Republic Bank", "frc-first-republic"),
    ("SIVB", date(2018, 3, 19), date(2023, 3, 15), "SVB Financial Group", "sivb-svb"),
    ("ESRX", date(2003, 9, 26), date(2018, 12, 21), "Express Scripts Holding Company", "express-scripts"),
    ("DO", date(2009, 2, 26), date(2016, 10, 3), "Diamond Offshore", "do-diamond-offshore"),
    ("CHK", date(2006, 3, 3), date(2018, 3, 19), "Chesapeake Energy", "chk-chesapeake"),
    ("CA", date(1996, 1, 2), date(2018, 11, 6), "CA Technologies", "ca-technologies"),
    ("ADS", date(2013, 12, 23), date(2020, 6, 22), "Alliance Data / Bread Financial", "ads-alliance-data"),
)

ACQUIRER_ALIASES: dict[str, frozenset[str]] = {
    "ATVI": frozenset({"MSFT"}),
    "CELG": frozenset({"BMY"}),
    "XLNX": frozenset({"AMD"}),
    "ESRX": frozenset({"CI"}),
}

SEA_TRIAL_ASSET_ID = "2326776"
CATEGORY_A_TICKERS: frozenset[str] = frozenset(
    {"ATVI", "CELG", "XLNX", "FRC", "SIVB", "ESRX"}
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_PARTIAL = "PARTIAL"
STATUS_NOT_TESTABLE = "NOT_TESTABLE"
STATUS_MAPPED = "MAPPED"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_CONFLICT = "CONFLICT"

VERDICT_SUITABLE = "SUITABLE"
VERDICT_PARTIALLY_SUITABLE = "PARTIALLY SUITABLE"
VERDICT_NOT_SUITABLE = "NOT SUITABLE"
VERDICT_NOT_TESTABLE = "NOT_TESTABLE"

ALLOWED_PARTIAL_RESIDUALS: frozenset[str] = frozenset(
    {
        "tko_surviving_entity",
        "unofficial_fja05680_membership",
        "pre_window_delisted_not_testable",
    }
)

DELISTED_SUFFIX_PATTERN = r"^([A-Z0-9.\-]+)-(\d{6})$"
MAX_INTERIOR_GAP_DAYS = 14
BAR_CSV_FIELDS: tuple[str, ...] = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)
OCCUPANCY_CSV_FIELDS: tuple[str, ...] = (
    "pit_ticker",
    "occupancy_start",
    "occupancy_end",
    "expected_identity",
    "seed_key",
    "norgate_symbol",
    "norgate_asset_id",
    "security_name",
    "first_quoted",
    "last_quoted",
    "identity_source",
    "mapping_status",
    "notes",
)
