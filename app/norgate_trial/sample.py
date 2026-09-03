"""Load the frozen vendor-coverage sample without treating scripts as a package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def load_probe_vendor_coverage() -> ModuleType:
    """Import ``scripts/probe_vendor_coverage.py`` by file path.

    The existing probe is not a package. CLI runs of Platinum scripts cannot
    rely on ``from scripts.probe_vendor_coverage import ...``.
    """
    cached = sys.modules.get("probe_vendor_coverage")
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe_vendor_coverage.py"
    spec = importlib.util.spec_from_file_location("probe_vendor_coverage", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load frozen sample from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_vendor_coverage"] = module
    spec.loader.exec_module(module)
    return module


def frozen_sample() -> tuple[Any, ...]:
    module = load_probe_vendor_coverage()
    samples = getattr(module, "FROZEN_SAMPLE")
    return tuple(samples)
