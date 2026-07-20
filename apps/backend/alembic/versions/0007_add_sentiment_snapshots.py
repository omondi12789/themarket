"""add sentiment_snapshots table

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sentiment_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query", sa.String(64), nullable=False),
        sa.Column("mean_score", sa.Float, nullable=False),
        sa.Column("n_headlines", sa.Integer, nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("news_source", sa.String(32), nullable=False),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sentiment_snapshots_query", "sentiment_snapshots", ["query"])


def downgrade() -> None:
    op.drop_table("sentiment_snapshots")
