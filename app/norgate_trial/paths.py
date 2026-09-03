"""Isolated output paths for the Platinum trial."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("audit/norgate_platinum_trial")

_FORBIDDEN_WRITE_STEMS: tuple[str, ...] = (
    "market_bars",
    "known_identities.json",
    "vendor_coverage_probe.csv",
    "vendor_coverage_probe.json",
    "factory.py",
)

_FORBIDDEN_PARENT_NAMES: tuple[str, ...] = (
    "norgate_trial",
    "raw",
    "processed",
    "security_master",
    "migrations",
)


class IsolationError(ValueError):
    """Raised when a trial script would write outside the Platinum tree."""


@dataclass(frozen=True)
class TrialLayout:
    root: Path
    environment: Path
    package_proof: Path
    frozen_csv: Path
    frozen_json: Path
    occupancy: Path
    suffix_discovery: Path
    conflicts: Path
    totalreturn_dir: Path
    unadjusted_dir: Path
    membership_crosscheck: Path
    frozen_matrix: Path
    pit_coverage: Path
    identity_gates: Path
    adjustment_checks: Path
    verdict: Path


def trial_layout(output_dir: Path | None = None) -> TrialLayout:
    root = (output_dir or DEFAULT_OUTPUT_DIR).resolve()
    mapping = root / "mapping"
    bars = root / "bars"
    validation = root / "validation"
    return TrialLayout(
        root=root,
        environment=root / "environment.json",
        package_proof=root / "package_proof.json",
        frozen_csv=root / "frozen_sample.csv",
        frozen_json=root / "frozen_sample.json",
        occupancy=mapping / "occupancy.csv",
        suffix_discovery=mapping / "suffix_discovery.csv",
        conflicts=mapping / "conflicts.csv",
        totalreturn_dir=bars / "totalreturn",
        unadjusted_dir=bars / "unadjusted",
        membership_crosscheck=root / "membership_crosscheck" / "spx_vs_fja05680.csv",
        frozen_matrix=validation / "frozen_matrix.csv",
        pit_coverage=validation / "pit_coverage.csv",
        identity_gates=validation / "identity_gates.csv",
        adjustment_checks=validation / "adjustment_checks.csv",
        verdict=root / "verdict.json",
    )


def assert_trial_output_dir(path: Path) -> Path:
    """Return ``path`` if it is under audit/norgate_platinum_trial.

    Rejects the Trial artifact directory, production data, and Security Master
    seeds. Comparison is on resolved path parts so relative and absolute
    destinations both work.
    """
    resolved = path.expanduser().resolve()
    parts = {part.lower() for part in resolved.parts}
    if "norgate_platinum_trial" not in parts:
        raise IsolationError(
            f"Platinum trial output must be under audit/norgate_platinum_trial; got {path}"
        )
    if "norgate_trial" in parts and "norgate_platinum_trial" not in parts:
        raise IsolationError(f"refusing to overwrite Trial artifacts: {path}")
    name = resolved.name.lower()
    if name in {item.lower() for item in _FORBIDDEN_WRITE_STEMS}:
        raise IsolationError(f"refusing to write production artifact: {path}")
    parent_name = resolved.parent.name.lower()
    if parent_name in _FORBIDDEN_PARENT_NAMES and "norgate_platinum_trial" not in {
        part.lower() for part in resolved.parent.parts
    }:
        raise IsolationError(f"refusing to write production path: {path}")
    return resolved


def ensure_layout(layout: TrialLayout) -> TrialLayout:
    assert_trial_output_dir(layout.root)
    for directory in (
        layout.root,
        layout.occupancy.parent,
        layout.totalreturn_dir,
        layout.unadjusted_dir,
        layout.membership_crosscheck.parent,
        layout.frozen_matrix.parent,
    ):
        assert_trial_output_dir(directory)
        directory.mkdir(parents=True, exist_ok=True)
    return layout


def assert_not_production_write(path: Path) -> None:
    """Refuse paths that would mutate production data or the Trial baseline."""
    resolved = path.expanduser().resolve()
    parts = [part.lower() for part in resolved.parts]
    name = resolved.name.lower()
    if name in {item.lower() for item in _FORBIDDEN_WRITE_STEMS}:
        raise IsolationError(f"refusing to write production artifact: {path}")
    if "norgate_trial" in parts and "norgate_platinum_trial" not in parts:
        raise IsolationError(f"refusing to overwrite Trial artifacts: {path}")
    if "data" in parts and "raw" in parts:
        raise IsolationError(f"refusing to write data/raw: {path}")
    if "security_master" in parts and name == "known_identities.json":
        raise IsolationError(f"refusing to write Security Master seeds: {path}")
    if name == "factory.py":
        raise IsolationError(f"refusing to write production factory: {path}")
