from datetime import date
from pathlib import Path

import pytest

from app.security_master.catalog import InMemorySecurityMaster
from app.security_master.exceptions import SecurityMasterValidationError
from app.security_master.models import Security, SecurityTicker
from app.security_master.seed import load_known_identities_catalog
from app.security_master.validation import intervals_overlap, validate_tickers


def _security(seed_key: str) -> Security:
    return Security(seed_key=seed_key, display_name=seed_key)


def _listing(
    seed_key: str,
    ticker: str,
    start: date,
    end: date | None = None,
    *,
    scheme: str = "listing",
) -> SecurityTicker:
    return SecurityTicker(
        seed_key=seed_key,
        scheme=scheme,
        ticker=ticker,
        valid_from=start,
        valid_to=end,
    )


@pytest.mark.unit
def test_invariant_ticker_cannot_resolve_to_two_securities_on_same_date() -> None:
    overlapping = (
        _listing("a", "SE", date(2010, 1, 1), date(2020, 1, 1)),
        _listing("b", "SE", date(2015, 1, 1), date(2025, 1, 1)),
    )
    with pytest.raises(SecurityMasterValidationError, match="overlapping"):
        InMemorySecurityMaster((_security("a"), _security("b")), overlapping)


@pytest.mark.unit
def test_invariant_same_ticker_different_dates_different_securities() -> None:
    master = InMemorySecurityMaster(
        (_security("spectra-energy"), _security("sea-limited")),
        (
            _listing("spectra-energy", "SE", date(2007, 1, 3), date(2017, 2, 27)),
            _listing("sea-limited", "SE", date(2017, 10, 20)),
        ),
    )
    first = master.resolve_security("SE", date(2015, 6, 1))
    second = master.resolve_security("SE", date(2018, 6, 1))
    assert first.is_resolved and second.is_resolved
    assert first.security is not None and second.security is not None
    assert first.security.seed_key != second.security.seed_key


@pytest.mark.unit
def test_invariant_ticker_change_preserves_security_identity() -> None:
    master = load_known_identities_catalog()
    sq = master.resolve_security("SQ", date(2020, 1, 2))
    xyz = master.resolve_security("XYZ", date(2025, 6, 1))
    assert sq.is_resolved and xyz.is_resolved
    assert sq.security is not None and xyz.security is not None
    assert sq.security.seed_key == xyz.security.seed_key == "block-inc-class-a"
    history = master.get_ticker_history("block-inc-class-a")
    assert [item.ticker for item in history] == ["SQ", "XYZ"]


@pytest.mark.unit
def test_invariant_ticker_recycling_creates_different_ids() -> None:
    master = load_known_identities_catalog()
    spectra = master.resolve_security("SE", date(2015, 6, 1))
    sea = master.resolve_security("SE", date(2018, 6, 1))
    assert spectra.security is not None and sea.security is not None
    assert spectra.security.seed_key == "spectra-energy"
    assert sea.security.seed_key == "sea-limited"


@pytest.mark.unit
def test_invariant_unknown_identity_is_unresolved() -> None:
    master = load_known_identities_catalog()
    result = master.resolve_security("MSFT", date(2020, 1, 2))
    assert result.is_resolved is False
    assert result.security is None
    assert master.resolve_security("SE", date(2017, 6, 1)).is_resolved is False


@pytest.mark.unit
def test_invariant_vendor_bars_outside_validity_are_not_mapped() -> None:
    master = load_known_identities_catalog()
    before = master.resolve_market_data_symbol("TKO", date(2020, 1, 2))
    after = master.resolve_market_data_symbol("TKO", date(2024, 1, 2))
    assert before.is_resolved is False
    assert after.is_resolved
    assert after.security is not None
    assert after.security.seed_key == "tko-group-holdings"


@pytest.mark.unit
def test_adjacent_half_open_intervals_do_not_overlap() -> None:
    left = _listing("a", "XYZ", date(2015, 11, 19), date(2025, 1, 21))
    right = _listing("a", "XYZ", date(2025, 1, 21))
    assert intervals_overlap(left, right) is False
    report = validate_tickers((left, right))
    assert report.has_blocking_errors is False


@pytest.mark.unit
def test_security_master_package_has_no_ticker_blacklist() -> None:
    root = Path("app/security_master")
    forbidden = ("BLACKLIST", "EXCLUDE_TICKERS", "SUSPICIOUS_BLOCKLIST")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path} contains {token}"
        assert '{"XYZ", "TKO", "SE", "HAR"}' not in text
        assert "['XYZ', 'TKO', 'SE', 'HAR']" not in text
