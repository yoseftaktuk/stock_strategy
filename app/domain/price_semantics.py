"""Canonical price roles for the backtest. Roles are not interchangeable fields.

Execution, mark, signal, and terminal prices are different jobs. Mapping them
onto vendor columns is a tape capability, not a rename of ``close``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.domain.exceptions import DomainValidationError
from app.domain.models.market_bar import MarketBar


class PriceRole(str, Enum):
    EXECUTION = "EXECUTION"
    MARK = "MARK"
    SIGNAL = "SIGNAL"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class PriceSemantics:
    """Which vendor field fills each role on the current engine path.

    ``close_is_raw_unadjusted`` is False on the Yahoo tape: Close is
    split-adjusted OHLC, not a raw print. See ``TapeCapabilities``.
    """

    execution_field: str = "open"
    execution_session: str = "next_session"
    mark_field: str = "close"
    signal_field: str = "adjusted_close"
    terminal_field: str = "close"
    terminal_slippage: bool = False
    close_is_raw_unadjusted: bool = False


@dataclass(frozen=True)
class TapeCapabilities:
    """What the loaded tape can and cannot support without a new source."""

    vendor: str
    split_adjusted_ohlc: bool
    dividend_adjusted_close: bool
    raw_unadjusted_ohlc: bool
    split_events: bool
    cash_dividend_events: bool
    merger_terms: bool
    delisting_proceeds: bool
    known_delisting_last_close_proxy: bool


CANONICAL_PRICE_SEMANTICS = PriceSemantics()

YAHOO_CURRENT_TAPE = TapeCapabilities(
    vendor="yfinance auto_adjust=False → CSV/PostgreSQL market_bars",
    split_adjusted_ohlc=True,
    dividend_adjusted_close=True,
    raw_unadjusted_ohlc=False,
    split_events=False,
    cash_dividend_events=False,
    merger_terms=False,
    delisting_proceeds=False,
    known_delisting_last_close_proxy=True,
)


def price_for_role(bar: MarketBar, role: PriceRole) -> Decimal:
    """Return the vendor field used for ``role``. Never substitutes Adj Close for execution/mark/terminal."""
    if role is PriceRole.EXECUTION:
        return bar.open
    if role is PriceRole.MARK:
        return bar.close
    if role is PriceRole.TERMINAL:
        return bar.close
    if role is PriceRole.SIGNAL:
        if bar.adjusted_close is None:
            raise DomainValidationError(
                f"signal price requires adjusted_close symbol={bar.symbol}"
            )
        return bar.adjusted_close
    raise DomainValidationError(f"unknown price role {role}")
