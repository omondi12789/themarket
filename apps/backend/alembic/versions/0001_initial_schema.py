"""initial schema: users, trading_accounts, orders, positions

Revision ID: 0001
Revises:
Create Date: 2026-07-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("trader", "admin", "compliance", "support", name="user_role"),
            nullable=False,
            server_default="trader",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "trading_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "broker_type", sa.Enum("mt5", "mt4", "metaapi", name="broker_type"), nullable=False
        ),
        sa.Column("broker_login", sa.String(64), nullable=False),
        sa.Column("broker_server", sa.String(128), nullable=False),
        sa.Column("encrypted_credentials", sa.String(2048), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("balance", sa.Numeric(18, 2), server_default="0"),
        sa.Column("equity", sa.Numeric(18, 2), server_default="0"),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_trading_accounts_user_id", "trading_accounts", ["user_id"])

    order_side = sa.Enum("buy", "sell", name="order_side")
    order_side.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column(
            "order_type",
            sa.Enum("market", "limit", "stop", "stop_limit", name="order_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "submitted",
                "filled",
                "partially_filled",
                "cancelled",
                "rejected",
                name="order_status",
            ),
            server_default="pending",
        ),
        sa.Column("volume", sa.Numeric(18, 4), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 6), nullable=True),
        sa.Column("take_profit", sa.Numeric(18, 6), nullable=True),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("strategy_tag", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_strategy_tag", "orders", ["strategy_tag"])
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"])

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("side", order_side, nullable=False),
        sa.Column("volume", sa.Numeric(18, 4), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("stop_loss", sa.Numeric(18, 6), nullable=True),
        sa.Column("take_profit", sa.Numeric(18, 6), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(18, 2), server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_positions_account_id", "positions", ["account_id"])
    op.create_index("ix_positions_symbol", "positions", ["symbol"])


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("trading_accounts")
    op.drop_table("users")
    sa.Enum(name="order_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="order_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="order_side").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="broker_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
