"""add copy_trading_links table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "copy_trading_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "follower_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scaling_mode",
            sa.Enum("fixed_ratio", "equity_proportional", name="scaling_mode"),
            nullable=False,
        ),
        sa.Column("scaling_value", sa.Numeric(10, 4), server_default="1.0"),
        sa.Column("max_follower_volume", sa.Numeric(18, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copy_trading_links_source_account_id", "copy_trading_links", ["source_account_id"])
    op.create_index("ix_copy_trading_links_follower_account_id", "copy_trading_links", ["follower_account_id"])


def downgrade() -> None:
    op.drop_table("copy_trading_links")
    sa.Enum(name="scaling_mode").drop(op.get_bind(), checkfirst=True)
