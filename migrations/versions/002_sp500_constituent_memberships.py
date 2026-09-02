"""Add historical S&P 500 constituent memberships.

Revision ID: 002
Revises: 001
Create Date: 2026-09-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sp500_constituent_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("source_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sp500_constituent_memberships_pit",
        "sp500_constituent_memberships",
        ["symbol", "start_date", "end_date"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sp500_constituent_memberships_interval
        ON sp500_constituent_memberships
        (symbol, start_date, COALESCE(end_date, DATE '9999-12-31'))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sp500_constituent_memberships_interval")
    op.drop_index(
        "ix_sp500_constituent_memberships_pit",
        table_name="sp500_constituent_memberships",
    )
    op.drop_table("sp500_constituent_memberships")
