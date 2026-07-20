"""add predictions table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("probability_up", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("model_type", sa.String(128), nullable=False),
        sa.Column("cv_accuracy_mean", sa.Float, nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("actual_direction", sa.String(4), nullable=True),
        sa.Column("was_correct", sa.Boolean, nullable=True),
    )
    op.create_index("ix_predictions_symbol", "predictions", ["symbol"])
    op.create_index("ix_predictions_as_of", "predictions", ["as_of"])


def downgrade() -> None:
    op.drop_table("predictions")
