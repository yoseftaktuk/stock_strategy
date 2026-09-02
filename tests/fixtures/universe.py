from datetime import date

from app.universe.models import ConstituentMembership

SOURCE = "test-fixture"


def membership(
    symbol: str,
    start: date,
    end: date | None = None,
) -> ConstituentMembership:
    return ConstituentMembership(
        symbol=symbol,
        start_date=start,
        end_date=end,
        source=SOURCE,
        source_version="fixture",
    )


def survivorship_memberships() -> tuple[ConstituentMembership, ...]:
    """Deterministic AAA/BBB/CCC/DDD/EEE survivorship regression fixture.

    2015: AAA BBB CCC
    2020: AAA CCC DDD
    2025: AAA DDD EEE
    """
    return (
        membership("AAA", date(2010, 1, 1), None),
        membership("BBB", date(2010, 1, 1), date(2020, 1, 1)),
        membership("CCC", date(2010, 1, 1), date(2025, 1, 1)),
        membership("DDD", date(2020, 1, 1), None),
        membership("EEE", date(2025, 1, 1), None),
    )


def late_entrant_memberships() -> tuple[ConstituentMembership, ...]:
    """AAA is a current constituent that only entered in 2020.

    Used to catch the classic survivorship bug: a name with strong 2015
    momentum must not be selectable in 2015 under a point-in-time universe.
    """
    return (
        membership("AAA", date(2020, 1, 1), None),
        membership("BBB", date(2010, 1, 1), None),
        membership("CCC", date(2010, 1, 1), None),
    )
