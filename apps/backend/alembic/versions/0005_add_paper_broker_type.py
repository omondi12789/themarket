"""add paper broker type

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE broker_type ADD VALUE IF NOT EXISTS 'paper'")


def downgrade() -> None:
    # Postgres doesn't support removing enum values directly; a real downgrade would
    # require rebuilding the enum type and is deliberately left as a manual step
    # (this is the standard, documented Postgres enum limitation).
    pass
