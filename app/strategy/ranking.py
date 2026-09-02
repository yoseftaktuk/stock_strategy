from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MomentumCandidate:
    symbol: str
    date: date
    momentum: Decimal


def rank_candidates(candidates: Sequence[MomentumCandidate]) -> list[MomentumCandidate]:
    """Sort by momentum descending, then symbol ascending for ties."""
    return sorted(candidates, key=lambda candidate: (-candidate.momentum, candidate.symbol))


def select_top_n(
    ranked: Sequence[MomentumCandidate],
    top_n: int,
) -> list[MomentumCandidate]:
    """Return the first ``top_n`` candidates. Does not pad if fewer qualify."""
    return list(ranked[:top_n])
