"""add strategies and strategy_trades tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tag", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("capital_allocation_pct", sa.Numeric(5, 4), server_default="0"),
        sa.Column("min_allocation_pct", sa.Numeric(5, 4), server_default="0"),
        sa.Column("max_allocation_pct", sa.Numeric(5, 4), server_default="1"),
        sa.Column("last_reallocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategies_tag", "strategies", ["tag"])

    op.create_table(
        "strategy_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_tag", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 2), nullable=False),
        sa.Column("return_pct", sa.Numeric(10, 6), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategy_trades_strategy_tag", "strategy_trades", ["strategy_tag"])


def downgrade() -> None:
    op.drop_table("strategy_trades")
    op.drop_table("strategies")
