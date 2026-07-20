"""add rl_sizing_suggestions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rl_sizing_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("suggested_size", sa.Float, nullable=False),
        sa.Column("action_index", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("agent_trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rl_sizing_suggestions_symbol", "rl_sizing_suggestions", ["symbol"])


def downgrade() -> None:
    op.drop_table("rl_sizing_suggestions")
