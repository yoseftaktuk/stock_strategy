from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.csv_cache import read_normalized_csv
from app.domain.exceptions import DomainValidationError
from app.domain.price_semantics import (
    CANONICAL_PRICE_SEMANTICS,
    PriceRole,
    YAHOO_CURRENT_TAPE,
    price_for_role,
)
from tests.fixtures.momentum import make_bar

SPLIT_FIXTURE = Path("tests/data/yahoo_aapl_2020_split.csv")


def _bar(*, close: Decimal, open: Decimal, adjusted: Decimal):
    return make_bar(
        "AAPL",
        date(2020, 8, 28),
        close=close,
        open=open,
        adjusted_close=adjusted,
    )


@pytest.mark.unit
def test_canonical_roles_are_distinct_fields() -> None:
    semantics = CANONICAL_PRICE_SEMANTICS
    assert semantics.execution_field == "open"
    assert semantics.execution_session == "next_session"
    assert semantics.mark_field == "close"
    assert semantics.signal_field == "adjusted_close"
    assert semantics.terminal_field == "close"
    assert semantics.terminal_slippage is False
    assert semantics.close_is_raw_unadjusted is False
    assert semantics.signal_field != semantics.execution_field
    assert semantics.signal_field != semantics.mark_field
    assert semantics.signal_field != semantics.terminal_field


@pytest.mark.unit
def test_price_for_role_never_uses_adjusted_close_for_accounting() -> None:
    bar = _bar(close=Decimal("100"), open=Decimal("99"), adjusted=Decimal("80"))
    assert price_for_role(bar, PriceRole.EXECUTION) == Decimal("99")
    assert price_for_role(bar, PriceRole.MARK) == Decimal("100")
    assert price_for_role(bar, PriceRole.TERMINAL) == Decimal("100")
    assert price_for_role(bar, PriceRole.SIGNAL) == Decimal("80")
    assert price_for_role(bar, PriceRole.TERMINAL) != bar.adjusted_close
    assert price_for_role(bar, PriceRole.EXECUTION) != bar.adjusted_close
    assert price_for_role(bar, PriceRole.MARK) != bar.adjusted_close


@pytest.mark.unit
def test_signal_price_requires_adjusted_close() -> None:
    bar = make_bar("AAPL", date(2020, 8, 28), close=Decimal("100"), missing_adjusted_close=True)
    with pytest.raises(DomainValidationError, match="adjusted_close"):
        price_for_role(bar, PriceRole.SIGNAL)


@pytest.mark.unit
def test_yahoo_tape_cannot_support_raw_events_or_unadjusted_ohlc() -> None:
    tape = YAHOO_CURRENT_TAPE
    assert tape.split_adjusted_ohlc is True
    assert tape.dividend_adjusted_close is True
    assert tape.raw_unadjusted_ohlc is False
    assert tape.split_events is False
    assert tape.cash_dividend_events is False
    assert tape.merger_terms is False
    assert tape.delisting_proceeds is False
    assert tape.known_delisting_last_close_proxy is True


@pytest.mark.unit
def test_yahoo_close_is_not_raw_unadjusted_across_aapl_split() -> None:
    bars = read_normalized_csv(SPLIT_FIXTURE)
    assert len(bars) == 2
    pre, post = bars
    assert pre.timestamp.date() == date(2020, 8, 28)
    assert post.timestamp.date() == date(2020, 8, 31)
    # A 4-for-1 split; raw unadjusted close would drop from ~$500 to ~$125.
    assert pre.close < Decimal("200")
    ratio = post.close / pre.close
    assert Decimal("0.8") < ratio < Decimal("1.2")
    assert pre.adjusted_close is not None and post.adjusted_close is not None
    assert pre.adjusted_close < pre.close
    assert post.adjusted_close < post.close


@pytest.mark.unit
def test_engine_terminal_path_uses_close_not_adjusted_close() -> None:
    text = Path("app/backtest/engine.py").read_text(encoding="utf-8")
    assert "last_prices[symbol] = last.close" in text
    assert "last.adjusted_close" not in text
    assert "liquidate_at" in text


@pytest.mark.unit
def test_momentum_module_uses_adjusted_close_only() -> None:
    text = Path("app/strategy/calculations.py").read_text(encoding="utf-8")
    assert "_require_adjusted_close" in text
    assert "skip_price = _require_adjusted_close" in text
    assert "lookback_price = _require_adjusted_close" in text
