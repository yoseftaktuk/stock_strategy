"""JSON/CSV helpers and environment capture for Platinum trial artifacts."""

from __future__ import annotations

import csv
import json
import platform
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.norgate_trial.paths import assert_trial_output_dir


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    assert_trial_output_dir(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return raw


def write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    assert_trial_output_dir(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def environment_payload(*, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "trial": "norgate_platinum",
        "production_writes": False,
        "research_ready": False,
        "phase_5": "NOT STARTED",
    }
    if extra:
        payload.update(dict(extra))
    return payload
