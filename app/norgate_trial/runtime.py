"""Load norgatedata when NDU is available. Never a production provider."""

from __future__ import annotations

from typing import Any

from app.norgate_trial.constants import DELISTED_DATABASE_NAME, LISTED_DATABASE_NAME


def import_norgatedata() -> tuple[Any | None, str]:
    try:
        import norgatedata  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    return norgatedata, ""


def norgate_status(module: Any) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    running = False
    status_fn = getattr(module, "status", None)
    if callable(status_fn):
        try:
            running = bool(status_fn())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"status() failed: {exc}")
    else:
        errors.append("norgatedata.status is not callable.")
    names: list[str] = []
    databases_fn = getattr(module, "databases", None)
    if callable(databases_fn):
        try:
            names = [str(item) for item in databases_fn()]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"databases() failed: {exc}")
    if not running:
        errors.append("NDU is not running.")
    return running, names, errors


def has_database(names: list[str], expected: str) -> bool:
    return any(name.casefold() == expected.casefold() for name in names)


def listed_and_delisted_present(names: list[str]) -> tuple[bool, bool]:
    return has_database(names, LISTED_DATABASE_NAME), has_database(names, DELISTED_DATABASE_NAME)
