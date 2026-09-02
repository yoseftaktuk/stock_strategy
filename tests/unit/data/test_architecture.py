from pathlib import Path

import pytest


FORBIDDEN_DOMAIN_IMPORTS = (
    "sqlalchemy",
    "pandas",
    "psycopg2",
    "streamlit",
    "plotly",
    "app.database",
    "app.broker",
    "app.data.providers",
)


@pytest.mark.unit
def test_domain_does_not_import_infrastructure() -> None:
    domain_root = Path("app/domain")
    for path in domain_root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for token in FORBIDDEN_DOMAIN_IMPORTS:
                assert token not in stripped, f"{path} imports {token}: {stripped}"


@pytest.mark.unit
def test_historical_provider_does_not_import_strategy_or_universe() -> None:
    path = Path("app/data/providers/historical.py")
    text = path.read_text(encoding="utf-8")
    assert "app.universe" not in text
    assert "app.backtest" not in text
    assert "app.strategy" not in text
    assert "streamlit" not in text


@pytest.mark.unit
def test_strategy_does_not_import_csv_provider() -> None:
    strategy_root = Path("app/strategy")
    for path in strategy_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "CSVMarketDataProvider" not in text
        assert "app.data.providers" not in text
