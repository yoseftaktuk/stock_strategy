#!/usr/bin/env python3
"""Import the evidence-backed Security Master catalog into PostgreSQL.

Loads data/security_master/known_identities.json. Does not download identifier
datasets. Re-running the import is idempotent. Does not alter PIT membership.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError
from app.database.repositories.security_master import PostgresSecurityMasterRepository
from app.database.session import ensure_database_available, session_scope
from app.security_master.exceptions import SecurityMasterSourceError, SecurityMasterValidationError
from app.security_master.seed import DEFAULT_SEED_PATH, load_known_identities_catalog
from app.security_master.service import SecurityMasterService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Security Master known identities into PostgreSQL.")
    parser.add_argument(
        "--source-file",
        type=Path,
        default=DEFAULT_SEED_PATH,
        help="Known-identities JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    settings = Settings()
    try:
        ensure_database_available(settings)
    except DatabaseConnectionError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    try:
        catalog = load_known_identities_catalog(args.source_file)
        payload = json.loads(args.source_file.read_text(encoding="utf-8"))
        source = str(payload.get("source") or "security-master-seed")
        source_version = str(payload.get("source_version") or "")
    except (OSError, json.JSONDecodeError, SecurityMasterSourceError, SecurityMasterValidationError) as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc

    try:
        with session_scope(settings) as session:
            repository = PostgresSecurityMasterRepository(session)
            service = SecurityMasterService(repository)
            summary = service.persist_catalog(
                catalog,
                source=source,
                source_version=source_version,
            )
    except SecurityMasterValidationError as exc:
        print(str(exc))
        raise SystemExit(1) from exc

    print(summary.format())
    print(f"Source file: {args.source_file}")


if __name__ == "__main__":
    main()
