"""Add Security Master tables alongside stocks, market_bars, and memberships.

Revision ID: 004
Revises: 003
Create Date: 2026-09-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("seed_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("security_type", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seed_key"),
    )
    op.create_table(
        "security_tickers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(length=20), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("continuity", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("source_version", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_tickers_scheme_ticker",
        "security_tickers",
        ["scheme", "ticker", "valid_from"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_security_tickers_interval
        ON security_tickers
        (scheme, ticker, valid_from, COALESCE(valid_to, DATE '9999-12-31'))
        """
    )
    op.create_table(
        "security_identifiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.Integer(), nullable=False),
        sa.Column("id_type", sa.String(length=20), nullable=False),
        sa.Column("id_value", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_security_identifiers_type_value_from
        ON security_identifiers
        (id_type, id_value, COALESCE(valid_from, DATE '0001-01-01'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_security_identifiers_type_value_from")
    op.drop_table("security_identifiers")
    op.execute("DROP INDEX IF EXISTS uq_security_tickers_interval")
    op.drop_index("ix_security_tickers_scheme_ticker", table_name="security_tickers")
    op.drop_table("security_tickers")
    op.drop_table("securities")
