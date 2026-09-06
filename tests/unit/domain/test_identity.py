import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.enums import OrderSide, OrderType
from app.domain.exceptions import DomainValidationError
from app.domain.models.identity import IdentityRef, PositionKey, position_key_for
from app.domain.models.listing import Listing, unknown_occupancy_listing_id
from app.domain.models.order import Order
from app.domain.models.security import RESOLUTION_UNRESOLVED


def _listing(*, ticker: str = "MSFT", security_id: str | None = None) -> Listing:
    return Listing(
        ticker=ticker,
        valid_from=date(2015, 1, 2),
        security_id=security_id,
    )


@pytest.mark.unit
def test_resolved_position_key_uses_security_id() -> None:
    listing = _listing(ticker="SQ", security_id="catalog:block-inc-class-a")
    identity = IdentityRef.resolved(
        security_id="catalog:block-inc-class-a",
        listing=listing,
        ticker_as_of="SQ",
    )
    assert identity.is_resolved
    assert identity.position_key() == PositionKey.for_security("catalog:block-inc-class-a")
    assert str(identity.position_key()) == "security:catalog:block-inc-class-a"
    assert identity.position_key() != PositionKey.for_listing(listing.listing_id)


@pytest.mark.unit
def test_unresolved_position_key_uses_listing_occupancy() -> None:
    listing = _listing(ticker="MSFT")
    identity = IdentityRef.unresolved(listing=listing, ticker_as_of="MSFT")
    assert identity.security_id is None
    assert identity.position_key() == PositionKey.for_listing(listing.listing_id)
    assert identity.position_key().kind == "listing"


@pytest.mark.unit
def test_unresolved_must_not_carry_a_security_id() -> None:
    with pytest.raises(DomainValidationError, match="UNRESOLVED"):
        IdentityRef(
            status=RESOLUTION_UNRESOLVED,
            ticker_as_of="MSFT",
            listing=_listing(ticker="MSFT", security_id="guessed"),
            security_id="guessed",
        )
    with pytest.raises(DomainValidationError, match="UNRESOLVED"):
        IdentityRef(
            status=RESOLUTION_UNRESOLVED,
            ticker_as_of="MSFT",
            listing=_listing(ticker="MSFT"),
            security_id="hash-of-msft",
        )


@pytest.mark.unit
def test_resolved_requires_security_id_on_listing() -> None:
    with pytest.raises(DomainValidationError, match="RESOLVED identity requires a listing security_id"):
        IdentityRef.resolved(
            security_id="catalog:x",
            listing=_listing(ticker="X"),
            ticker_as_of="X",
        )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.unit
def test_domain_identity_has_no_provider_imports() -> None:
    forbidden = {
        "norgatedata",
        "yfinance",
        "app.norgate_trial",
        "app.data.providers",
        "app.data.providers.csv",
        "app.data.providers.historical",
        "app.data.providers.offline",
        "app.data.providers.ibkr",
        "app.norgate_trial.client",
        "app.norgate_trial.occupancy",
    }
    paths = (
        Path("app/domain/identity.py"),
        Path("app/domain/models/identity.py"),
        Path("app/domain/models/listing.py"),
        Path("app/security_master/identity_resolver.py"),
    )
    for path in paths:
        imported = _imported_modules(path)
        overlap = imported & forbidden
        assert not overlap, f"{path} imports provider modules: {sorted(overlap)}"
        assert "norgatedata" not in path.read_text(encoding="utf-8")
        assert "yfinance" not in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_position_key_for_uses_identity_not_ticker() -> None:
    listing = _listing(ticker="SQ", security_id="catalog:block-inc-class-a")
    identity = IdentityRef.resolved(
        security_id="catalog:block-inc-class-a",
        listing=listing,
        ticker_as_of="SQ",
    )
    order = Order(
        symbol="SQ",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="sq-1",
        identity=identity,
    )
    assert position_key_for(order) == "security:catalog:block-inc-class-a"
    assert position_key_for(order) != "SQ"
    bare = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        limit_price=None,
        client_order_id="aapl-1",
    )
    expected = str(
        PositionKey.for_listing(unknown_occupancy_listing_id(ticker="AAPL", exchange=None))
    )
    assert position_key_for(bare) == expected
    assert position_key_for(bare) != "AAPL"


@pytest.mark.unit
def test_runtime_booking_keys_positions_by_position_key() -> None:
    broker_source = Path("app/broker/simulated.py").read_text(encoding="utf-8")
    assert "self._positions[order.symbol]" not in broker_source
    assert "position_key_for" in broker_source
    assert "CatalogIdentityResolver" not in broker_source
    assert "identity_resolver" not in broker_source
    order_source = Path("app/application/order_service.py").read_text(encoding="utf-8")
    assert "position_key_for" in order_source
    assert "_booked_by_position_key" in order_source
    risk_source = Path("app/risk/risk_manager.py").read_text(encoding="utf-8")
    assert "position_key_for" in risk_source
    assert "position.symbol == order.symbol" not in risk_source
    engine_source = Path("app/backtest/engine.py").read_text(encoding="utf-8")
    assert "attach_signal_identities" in engine_source
    assert "self._identity_resolver.resolve" not in engine_source
    strategy_source = Path("app/strategy/momentum.py").read_text(encoding="utf-8")
    assert "IdentityRef" not in strategy_source
    assert "CatalogIdentityResolver" not in strategy_source
