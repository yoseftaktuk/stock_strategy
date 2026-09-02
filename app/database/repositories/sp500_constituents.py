from collections.abc import Sequence
from datetime import date

from sqlalchemy import literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.mappers import sp500_constituent as membership_mapper
from app.database.models import SP500ConstituentMembershipModel
from app.universe.models import ConstituentMembership

DEFAULT_INSERT_BATCH_SIZE = 2000


class PostgresSP500ConstituentRepository:
    def __init__(self, session: Session, *, batch_size: int = DEFAULT_INSERT_BATCH_SIZE) -> None:
        self._session = session
        self._batch_size = batch_size

    def get_memberships(self, symbol: str) -> Sequence[ConstituentMembership]:
        stmt = (
            select(SP500ConstituentMembershipModel)
            .where(SP500ConstituentMembershipModel.symbol == symbol.strip().upper())
            .order_by(SP500ConstituentMembershipModel.start_date)
        )
        rows = self._session.scalars(stmt).all()
        return [membership_mapper.to_domain(row) for row in rows]

    def get_memberships_as_of(self, as_of: date) -> Sequence[ConstituentMembership]:
        stmt = (
            select(SP500ConstituentMembershipModel)
            .where(
                SP500ConstituentMembershipModel.start_date <= as_of,
                or_(
                    SP500ConstituentMembershipModel.end_date.is_(None),
                    as_of < SP500ConstituentMembershipModel.end_date,
                ),
            )
            .order_by(SP500ConstituentMembershipModel.symbol)
        )
        rows = self._session.scalars(stmt).all()
        return [membership_mapper.to_domain(row) for row in rows]

    def get_all_memberships(self) -> Sequence[ConstituentMembership]:
        stmt = select(SP500ConstituentMembershipModel).order_by(
            SP500ConstituentMembershipModel.symbol,
            SP500ConstituentMembershipModel.start_date,
        )
        rows = self._session.scalars(stmt).all()
        return [membership_mapper.to_domain(row) for row in rows]

    def upsert_memberships(self, memberships: Sequence[ConstituentMembership]) -> tuple[int, int]:
        if not memberships:
            return 0, 0

        rows = [membership_mapper.to_row(item) for item in memberships]
        inserted = 0
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            stmt = (
                insert(SP500ConstituentMembershipModel)
                .values(batch)
                .on_conflict_do_nothing(
                    index_elements=[
                        "symbol",
                        "start_date",
                        literal_column("COALESCE(end_date, DATE '9999-12-31')"),
                    ]
                )
                .returning(SP500ConstituentMembershipModel.id)
            )
            result = self._session.execute(stmt)
            inserted += len(result.all())

        self._session.flush()
        existing = len(memberships) - inserted
        return inserted, existing
