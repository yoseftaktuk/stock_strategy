from pathlib import Path

import pytest


FORBIDDEN_STRATEGY_IMPORTS = (
    "sqlalchemy",
    "ibkr",
    "pandas",
    "psycopg2",
    "streamlit",
    "plotly",
    "app.database",
    "app.broker",
    "app.data.providers",
    "app.universe.providers",
    "app.security_master",
    "submit_order",
    "get_account",
    "get_positions",
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


@pytest.mark.unit
def test_strategy_does_not_import_infrastructure() -> None:
    strategy_root = Path("app/strategy")
    for path in strategy_root.rglob("*.py"):
        for stripped in _import_lines(path):
            for token in FORBIDDEN_STRATEGY_IMPORTS:
                assert token not in stripped, f"{path} imports {token}: {stripped}"


@pytest.mark.unit
def test_strategy_does_not_submit_orders() -> None:
    strategy_root = Path("app/strategy")
    for path in strategy_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "submit_order" not in text
        assert "IBKRBroker" not in text
        assert "IBKRClient" not in text
