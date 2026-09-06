"""Pure corporate-action accounting. Separate from any market-data provider.

Rules:
- Splits scale quantity by factor and prices by 1/factor. Cash unchanged
  unless cash-in-lieu of fractions is requested.
- Cash dividends credit ``qty * amount`` on the economic date (ex-date).
  Quantity is unchanged. The tape is not rewritten.
- Rename does not resolve identity and does not change position_key.
- Share conversion / cash acquisition without explicit terms is UNRESOLVED.
- Events are never inferred from adjusted prices.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
from typing import Protocol

from app.domain.exceptions import DomainValidationError
from app.domain.models.corporate_action import (
    AccountingSnapshot,
    ActionApplication,
    CorporateAction,
    CorporateActionType,
    FractionalSharePolicy,
)
from app.domain.models.market_bar import MarketBar

_ZERO = Decimal("0")


class CorporateActionProvider(Protocol):
    """Source of dated events. The current Yahoo tape implements the empty provider."""

    def actions_on(self, effective_date: object) -> Sequence[CorporateAction]:
        ...


class EmptyCorporateActionProvider:
    """Current production tape: no split, dividend, or merger events."""

    def actions_on(self, effective_date: object) -> tuple[CorporateAction, ...]:
        return ()


def infer_actions_from_prices(bars: Sequence[MarketBar]) -> tuple[CorporateAction, ...]:
    """Refuse to mint events from Close / Adj Close.

    A changing ``close / adjusted_close`` ratio is not a split or dividend
    event. The current tape has no corporate-action rows to parse.
    """
    del bars
    return ()


def apply_action(
    snapshot: AccountingSnapshot,
    action: CorporateAction,
    *,
    fractional: FractionalSharePolicy = FractionalSharePolicy.KEEP_FRACTION,
    terminal_price: Decimal | None = None,
) -> tuple[AccountingSnapshot, ActionApplication]:
    """Apply one event. Missing merger/acquisition terms return UNRESOLVED."""
    if action.action_type is CorporateActionType.NO_ACTION:
        return snapshot, ActionApplication.APPLIED
    if action.action_type in {CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT}:
        return apply_split(snapshot, action, fractional=fractional), ActionApplication.APPLIED
    if action.action_type is CorporateActionType.CASH_DIVIDEND:
        return apply_cash_dividend(snapshot, action), ActionApplication.APPLIED
    if action.action_type is CorporateActionType.RENAME:
        return apply_rename(snapshot, action), ActionApplication.APPLIED
    if action.action_type is CorporateActionType.DELISTING:
        return apply_delisting(snapshot, terminal_price=terminal_price), ActionApplication.APPLIED
    if action.action_type is CorporateActionType.CASH_ACQUISITION:
        return apply_cash_acquisition(snapshot, action)
    if action.action_type is CorporateActionType.SHARE_CONVERSION:
        return snapshot, ActionApplication.UNRESOLVED
    raise DomainValidationError(f"unsupported action_type {action.action_type}")


def apply_split(
    snapshot: AccountingSnapshot,
    action: CorporateAction,
    *,
    fractional: FractionalSharePolicy = FractionalSharePolicy.KEEP_FRACTION,
) -> AccountingSnapshot:
    """Scale shares and per-share prices so economic value is unchanged.

    2-for-1: factor=2 → qty×2, price÷2, average_price÷2, cash unchanged.
    Reverse split uses factor < 1 (1-for-2 → 0.5) and is the same formula.
    """
    factor = action.factor
    if factor is None or factor <= 0:
        raise DomainValidationError("split requires factor > 0")
    new_qty = snapshot.quantity * factor
    new_avg = snapshot.average_price / factor
    new_px = snapshot.market_price / factor
    cash = snapshot.cash
    if fractional is FractionalSharePolicy.CASH_IN_LIEU:
        whole = new_qty.to_integral_value(rounding=ROUND_DOWN)
        remainder = new_qty - whole
        cash += remainder * new_px
        new_qty = whole
    elif fractional is not FractionalSharePolicy.KEEP_FRACTION:
        raise DomainValidationError(f"unknown fractional policy {fractional}")
    return replace(
        snapshot,
        quantity=new_qty,
        average_price=new_avg,
        market_price=new_px,
        cash=cash,
    )


def apply_cash_dividend(snapshot: AccountingSnapshot, action: CorporateAction) -> AccountingSnapshot:
    """Credit cash on ex-date. Quantity and per-share cost are unchanged.

    Payment date is settlement timing. Daily backtest accounting uses ex-date.
    Do not also rewrite ``adjusted_close``; that field already embeds dividends
    on the Yahoo tape and is a signal input, not a cash ledger.
    """
    amount = action.amount
    if amount is None:
        raise DomainValidationError("cash dividend requires amount per share")
    return replace(snapshot, cash=snapshot.cash + snapshot.quantity * amount)


def apply_rename(snapshot: AccountingSnapshot, action: CorporateAction) -> AccountingSnapshot:
    """Display ticker may change. Identity and position_key do not.

    A rename is not an identity resolver. SQ→XYZ continuity lives on the
    Security Master, not on this event.
    """
    ticker = action.ticker or snapshot.symbol
    return replace(snapshot, symbol=ticker)


def apply_delisting(
    snapshot: AccountingSnapshot,
    *,
    terminal_price: Decimal | None,
) -> AccountingSnapshot:
    """Close the held listing at last quoted close (not Adj Close), no slippage.

    Missing ``terminal_price`` is missing data, not authorization to invent a
    print. Known DELISTED vs missing tape is decided by the Security Master
    before this function is called.
    """
    if terminal_price is None or terminal_price <= 0:
        raise DomainValidationError("delisting requires a positive last quoted close")
    proceeds = snapshot.quantity * terminal_price
    return replace(
        snapshot,
        cash=snapshot.cash + proceeds,
        quantity=_ZERO,
        market_price=terminal_price,
    )


def apply_cash_acquisition(
    snapshot: AccountingSnapshot,
    action: CorporateAction,
) -> tuple[AccountingSnapshot, ActionApplication]:
    """Cash merger. Requires explicit cash-per-share terms.

    Last quoted close is not a substitute for conversion terms. Without
    ``amount`` the position is left unchanged and the outcome is UNRESOLVED.
    """
    if action.amount is None:
        return snapshot, ActionApplication.UNRESOLVED
    proceeds = snapshot.quantity * action.amount
    closed = replace(
        snapshot,
        cash=snapshot.cash + proceeds,
        quantity=_ZERO,
        market_price=action.amount,
    )
    return closed, ActionApplication.APPLIED
