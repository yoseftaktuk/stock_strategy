from pathlib import Path

import pytest

FORBIDDEN_UI_IMPORTS = (
    "sqlalchemy",
    "yfinance",
    "app.database.repositories",
    "app.database.models",
    "app.database.session",
    "PostgresMarketDataRepository",
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
def test_streamlit_does_not_import_database_or_yahoo() -> None:
    ui_root = Path("app/ui")
    for path in ui_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for stripped in _import_lines(path):
            for token in FORBIDDEN_UI_IMPORTS:
                assert token not in stripped, f"{path} imports {token}: {stripped}"
        assert "session.execute" not in text
