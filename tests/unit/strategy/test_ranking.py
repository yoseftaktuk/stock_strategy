from datetime import date
from decimal import Decimal

import pytest

from app.strategy.ranking import MomentumCandidate, rank_candidates, select_top_n


def _candidate(symbol: str, momentum: str) -> MomentumCandidate:
    return MomentumCandidate(
        symbol=symbol,
        date=date(2024, 1, 7),
        momentum=Decimal(momentum),
    )


@pytest.mark.unit
def test_rank_by_momentum_descending() -> None:
    ranked = rank_candidates(
        [
            _candidate("AAPL", "0.20"),
            _candidate("MSFT", "0.50"),
            _candidate("NVDA", "0.80"),
        ]
    )
    assert [item.symbol for item in ranked] == ["NVDA", "MSFT", "AAPL"]


@pytest.mark.unit
def test_rank_tie_breaks_by_symbol_ascending() -> None:
    ranked = rank_candidates(
        [
            _candidate("MSFT", "0.50"),
            _candidate("AAPL", "0.50"),
        ]
    )
    assert [item.symbol for item in ranked] == ["AAPL", "MSFT"]


@pytest.mark.unit
def test_rank_is_deterministic() -> None:
    candidates = [
        _candidate("NVDA", "0.80"),
        _candidate("AAPL", "0.50"),
        _candidate("MSFT", "0.50"),
        _candidate("AMD", "0.10"),
    ]
    first = rank_candidates(candidates)
    second = rank_candidates(list(reversed(candidates)))
    assert first == second


@pytest.mark.unit
def test_select_top_n_truncates() -> None:
    ranked = rank_candidates(
        [_candidate(f"S{index:02d}", str(Decimal("1") - Decimal(index) / 10)) for index in range(10)]
    )
    selected = select_top_n(ranked, 3)
    assert len(selected) == 3
    assert [item.symbol for item in selected] == ["S00", "S01", "S02"]


@pytest.mark.unit
def test_select_top_n_does_not_pad() -> None:
    ranked = rank_candidates(
        [
            _candidate("NVDA", "0.80"),
            _candidate("MSFT", "0.50"),
            _candidate("AAPL", "0.20"),
            _candidate("AMD", "0.10"),
        ]
    )
    selected = select_top_n(ranked, 10)
    assert len(selected) == 4
