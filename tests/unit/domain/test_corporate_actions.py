from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.corporate_actions import (
    EmptyCorporateActionProvider,
    apply_action,
    infer_actions_from_prices,
)
from app.domain.exceptions import DomainValidationError
from app.domain.models.corporate_action import (
    AccountingSnapshot,
    ActionApplication,
    CorporateAction,
    CorporateActionType,
    FractionalSharePolicy,
)
from app.domain.models.identity import IdentityRef
from app.domain.models.listing import Listing
from tests.fixtures.momentum import make_bar, make_series


def _identity(ticker: str, security_id: str) -> IdentityRef:
    listing = Listing(
        ticker=ticker,
        valid_from=date(2015, 1, 1),
        security_id=security_id,
    )
    return IdentityRef.resolved(
        security_id=security_id,
        listing=listing,
        ticker_as_of=ticker,
    )


def _snapshot(
    *,
    ticker: str = "ESRX",
    security_id: str = "express-scripts",
    quantity: Decimal = Decimal("100"),
    average_price: Decimal = Decimal("100"),
    market_price: Decimal = Decimal("100"),
    cash: Decimal = Decimal("1000"),
) -> AccountingSnapshot:
    return AccountingSnapshot(
        quantity=quantity,
        average_price=average_price,
        market_price=market_price,
        cash=cash,
        symbol=ticker,
        identity=_identity(ticker, security_id),
    )


@pytest.mark.unit
def test_split_preserves_economic_value_and_scales_basis() -> None:
    before = _snapshot()
    action = CorporateAction(
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2020, 8, 31),
        factor=Decimal("2"),
        source="contract-test",
        security_id="express-scripts",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after.quantity == Decimal("200")
    assert after.market_price == Decimal("50")
    assert after.average_price == Decimal("50")
    assert after.cash == before.cash
    assert after.economic_value == before.economic_value
    assert after.position_key() == before.position_key()


@pytest.mark.unit
def test_reverse_split_is_symmetric() -> None:
    before = _snapshot(quantity=Decimal("200"), average_price=Decimal("50"), market_price=Decimal("50"))
    action = CorporateAction(
        action_type=CorporateActionType.REVERSE_SPLIT,
        effective_date=date(2020, 8, 31),
        factor=Decimal("0.5"),
        source="contract-test",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after.quantity == Decimal("100")
    assert after.market_price == Decimal("100")
    assert after.average_price == Decimal("100")
    assert after.cash == before.cash
    assert after.economic_value == before.economic_value


@pytest.mark.unit
def test_split_cash_in_lieu_keeps_economic_value() -> None:
    before = _snapshot(quantity=Decimal("101"))
    action = CorporateAction(
        action_type=CorporateActionType.REVERSE_SPLIT,
        effective_date=date(2020, 1, 2),
        factor=Decimal("0.5"),
        source="contract-test",
    )
    kept, _ = apply_action(before, action, fractional=FractionalSharePolicy.KEEP_FRACTION)
    assert kept.quantity == Decimal("50.5")
    cashed, _ = apply_action(before, action, fractional=FractionalSharePolicy.CASH_IN_LIEU)
    assert cashed.quantity == Decimal("50")
    assert cashed.cash == before.cash + Decimal("0.5") * Decimal("200")
    assert cashed.economic_value == before.economic_value == kept.economic_value


@pytest.mark.unit
def test_cash_dividend_credits_cash_and_leaves_quantity() -> None:
    before = _snapshot(quantity=Decimal("100"), cash=Decimal("500"))
    action = CorporateAction(
        action_type=CorporateActionType.CASH_DIVIDEND,
        effective_date=date(2020, 5, 8),
        amount=Decimal("2"),
        source="contract-test",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after.quantity == before.quantity
    assert after.average_price == before.average_price
    assert after.market_price == before.market_price
    assert after.cash == Decimal("700")
    assert after.position_key() == before.position_key()


@pytest.mark.unit
def test_no_action_leaves_accounting_unchanged() -> None:
    before = _snapshot()
    action = CorporateAction(
        action_type=CorporateActionType.NO_ACTION,
        effective_date=date(2020, 1, 2),
        source="contract-test",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after == before


@pytest.mark.unit
def test_rename_does_not_change_identity_or_position_key() -> None:
    before = _snapshot(ticker="SQ", security_id="block-inc-class-a")
    action = CorporateAction(
        action_type=CorporateActionType.RENAME,
        effective_date=date(2025, 1, 21),
        ticker="XYZ",
        source="contract-test",
        security_id="block-inc-class-a",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after.symbol == "XYZ"
    assert after.identity == before.identity
    assert after.position_key() == before.position_key()
    assert after.position_key() == "security:block-inc-class-a"
    assert after.quantity == before.quantity
    assert after.cash == before.cash
    assert after.average_price == before.average_price


@pytest.mark.unit
def test_corporate_action_module_is_not_an_identity_resolver() -> None:
    text = Path("app/domain/corporate_actions.py").read_text(encoding="utf-8")
    assert "identity_resolver" not in text
    assert "SecurityMaster" not in text
    assert "resolve_security" not in text
    assert "infer_actions_from_prices" in text


@pytest.mark.unit
def test_delisting_closes_predecessor_at_last_close() -> None:
    before = _snapshot(ticker="ESRX", security_id="express-scripts", quantity=Decimal("10"))
    action = CorporateAction(
        action_type=CorporateActionType.DELISTING,
        effective_date=date(2018, 12, 21),
        ticker="ESRX",
        source="known-listing-termination",
        security_id="express-scripts",
    )
    last_close = Decimal("92.33")
    last_adj = Decimal("80")
    after, status = apply_action(before, action, terminal_price=last_close)
    assert status is ActionApplication.APPLIED
    assert after.quantity == Decimal("0")
    assert after.cash == before.cash + Decimal("10") * last_close
    assert after.cash != before.cash + Decimal("10") * last_adj
    assert after.position_key() == before.position_key()
    assert after.identity is not None
    assert after.identity.security_id == "express-scripts"
    assert after.identity.ticker_as_of == "ESRX"


@pytest.mark.unit
def test_cash_acquisition_without_terms_is_unresolved() -> None:
    before = _snapshot(ticker="ESRX", security_id="express-scripts")
    action = CorporateAction(
        action_type=CorporateActionType.CASH_ACQUISITION,
        effective_date=date(2018, 12, 20),
        ticker="ESRX",
        source="missing-terms",
        security_id="express-scripts",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.UNRESOLVED
    assert after == before


@pytest.mark.unit
def test_share_conversion_without_terms_is_unresolved() -> None:
    before = _snapshot(ticker="ESRX", security_id="express-scripts")
    action = CorporateAction(
        action_type=CorporateActionType.SHARE_CONVERSION,
        effective_date=date(2018, 12, 20),
        ticker="ESRX",
        source="missing-terms",
        security_id="express-scripts",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.UNRESOLVED
    assert after == before
    assert after.symbol != "CI"
    assert after.position_key() != "security:cigna"


@pytest.mark.unit
def test_cash_acquisition_with_terms_closes_for_cash() -> None:
    before = _snapshot(quantity=Decimal("10"), cash=Decimal("0"))
    action = CorporateAction(
        action_type=CorporateActionType.CASH_ACQUISITION,
        effective_date=date(2018, 12, 20),
        amount=Decimal("96.50"),
        source="explicit-terms",
    )
    after, status = apply_action(before, action)
    assert status is ActionApplication.APPLIED
    assert after.quantity == Decimal("0")
    assert after.cash == Decimal("965.00")
    assert after.position_key() == before.position_key()


@pytest.mark.unit
def test_missing_data_does_not_invent_corporate_actions() -> None:
    bars = make_series("AAPL", 5, start=date(2020, 8, 24), close=Decimal("50"))
    bars = list(bars)
    bars[-1] = make_bar(
        "AAPL",
        date(2020, 8, 28),
        close=Decimal("50"),
        adjusted_close=Decimal("10"),
    )
    assert infer_actions_from_prices(bars) == ()
    provider = EmptyCorporateActionProvider()
    assert provider.actions_on(date(2020, 8, 31)) == ()


@pytest.mark.unit
def test_split_factor_cannot_be_missing_or_non_positive() -> None:
    before = _snapshot()
    with pytest.raises(DomainValidationError, match="factor"):
        CorporateAction(
            action_type=CorporateActionType.SPLIT,
            effective_date=date(2020, 1, 2),
            factor=Decimal("0"),
            source="bad",
        )
    missing = CorporateAction(
        action_type=CorporateActionType.SPLIT,
        effective_date=date(2020, 1, 2),
        source="bad",
    )
    with pytest.raises(DomainValidationError, match="factor"):
        apply_action(before, missing)


@pytest.mark.unit
def test_delisting_without_last_close_is_not_invented() -> None:
    before = _snapshot()
    action = CorporateAction(
        action_type=CorporateActionType.DELISTING,
        effective_date=date(2018, 12, 21),
        source="missing-tape",
    )
    with pytest.raises(DomainValidationError, match="last quoted close"):
        apply_action(before, action, terminal_price=None)
