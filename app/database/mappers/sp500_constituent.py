from app.database.models import SP500ConstituentMembershipModel
from app.universe.models import ConstituentMembership


def to_domain(model: SP500ConstituentMembershipModel) -> ConstituentMembership:
    return ConstituentMembership(
        symbol=model.symbol,
        start_date=model.start_date,
        end_date=model.end_date,
        company_name=model.company_name,
        source=model.source,
        source_version=model.source_version,
        created_at=model.created_at,
    )


def to_row(membership: ConstituentMembership) -> dict[str, object]:
    return {
        "symbol": membership.symbol,
        "start_date": membership.start_date,
        "end_date": membership.end_date,
        "company_name": membership.company_name,
        "source": membership.source,
        "source_version": membership.source_version,
    }
