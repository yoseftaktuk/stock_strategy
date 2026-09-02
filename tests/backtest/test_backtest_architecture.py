from pathlib import Path

import pytest

FORBIDDEN = (
    "ibkr",
    "ib_insync",
    "ibapi",
    "IBKRBroker",
    "IBKRClient",
    "streamlit",
    "plotly",
    "yfinance",
)


def _import_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            lines.append(stripped)
    return lines


@pytest.mark.backtest
def test_backtest_and_strategy_do_not_import_ibkr() -> None:
    for root in (Path("app/backtest"), Path("app/strategy")):
        for path in root.rglob("*.py"):
            for stripped in _import_lines(path):
                for token in FORBIDDEN:
                    assert token not in stripped, f"{path} imports {token}: {stripped}"
