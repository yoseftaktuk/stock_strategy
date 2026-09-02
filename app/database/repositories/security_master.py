from collections.abc import Sequence

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.mappers import security as security_mapper
from app.database.models import SecurityIdentifierModel, SecurityModel, SecurityTickerModel
from app.domain.models.security import Security, SecurityIdentifier, SecurityTicker

DEFAULT_INSERT_BATCH_SIZE = 2000
OPEN_INTERVAL_SQL = "COALESCE(valid_to, DATE '9999-12-31')"
IDENTIFIER_FROM_SQL = "COALESCE(valid_from, DATE '0001-01-01')"


class PostgresSecurityMasterRepository:
    def __init__(self, session: Session, *, batch_size: int = DEFAULT_INSERT_BATCH_SIZE) -> None:
        self._session = session
        self._batch_size = batch_size

    def upsert_securities(self, securities: Sequence[Security]) -> tuple[int, int]:
        if not securities:
            return 0, 0
        rows = [security_mapper.security_to_row(item) for item in securities]
        inserted = 0
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            stmt = (
                insert(SecurityModel)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["seed_key"])
                .returning(SecurityModel.id)
            )
            result = self._session.execute(stmt)
            inserted += len(result.all())
        self._session.flush()
        return inserted, len(securities) - inserted

    def upsert_tickers(self, tickers: Sequence[SecurityTicker]) -> tuple[int, int]:
        if not tickers:
            return 0, 0
        ids = self._security_ids_by_seed()
        rows = [
            security_mapper.ticker_to_row(item, security_id=ids[item.seed_key])
            for item in tickers
            if item.seed_key in ids
        ]
        if not rows:
            return 0, 0
        inserted = 0
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            stmt = (
                insert(SecurityTickerModel)
                .values(batch)
                .on_conflict_do_nothing(
                    index_elements=[
                        "scheme",
                        "ticker",
                        "valid_from",
                        literal_column(OPEN_INTERVAL_SQL),
                    ]
                )
                .returning(SecurityTickerModel.id)
            )
            result = self._session.execute(stmt)
            inserted += len(result.all())
        self._session.flush()
        return inserted, len(rows) - inserted

    def upsert_identifiers(self, identifiers: Sequence[SecurityIdentifier]) -> tuple[int, int]:
        if not identifiers:
            return 0, 0
        ids = self._security_ids_by_seed()
        rows = [
            security_mapper.identifier_to_row(item, security_id=ids[item.seed_key])
            for item in identifiers
            if item.seed_key in ids
        ]
        if not rows:
            return 0, 0
        inserted = 0
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            stmt = (
                insert(SecurityIdentifierModel)
                .values(batch)
                .on_conflict_do_nothing(
                    index_elements=[
                        "id_type",
                        "id_value",
                        literal_column(IDENTIFIER_FROM_SQL),
                    ]
                )
                .returning(SecurityIdentifierModel.id)
            )
            result = self._session.execute(stmt)
            inserted += len(result.all())
        self._session.flush()
        return inserted, len(rows) - inserted

    def load_all(
        self,
    ) -> tuple[tuple[Security, ...], tuple[SecurityTicker, ...], tuple[SecurityIdentifier, ...]]:
        security_rows = self._session.scalars(
            select(SecurityModel).order_by(SecurityModel.seed_key)
        ).all()
        securities = tuple(security_mapper.security_to_domain(row) for row in security_rows)
        seed_by_id = {row.id: row.seed_key for row in security_rows}

        ticker_rows = self._session.scalars(
            select(SecurityTickerModel).order_by(
                SecurityTickerModel.scheme,
                SecurityTickerModel.ticker,
                SecurityTickerModel.valid_from,
            )
        ).all()
        tickers = tuple(
            security_mapper.ticker_to_domain(row, seed_key=seed_by_id[row.security_id])
            for row in ticker_rows
            if row.security_id in seed_by_id
        )

        identifier_rows = self._session.scalars(
            select(SecurityIdentifierModel).order_by(
                SecurityIdentifierModel.id_type,
                SecurityIdentifierModel.id_value,
            )
        ).all()
        identifiers = tuple(
            security_mapper.identifier_to_domain(row, seed_key=seed_by_id[row.security_id])
            for row in identifier_rows
            if row.security_id in seed_by_id
        )
        return securities, tickers, identifiers

    def _security_ids_by_seed(self) -> dict[str, int]:
        rows = self._session.scalars(select(SecurityModel)).all()
        return {row.seed_key: row.id for row in rows}
