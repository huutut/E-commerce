"""add inventory adjustment tracking

Revision ID: 20260801_0003
Revises: 20260801_0002
Create Date: 2026-08-01 01:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0003"
down_revision: str | None = "20260801_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="10"),
    )
    op.alter_column("products", "low_stock_threshold", server_default=None)

    op.create_table(
        "inventory_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("change_quantity", sa.Integer(), nullable=False),
        sa.Column("stock_before", sa.Integer(), nullable=False),
        sa.Column("stock_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_adjustments_actor_id", "inventory_adjustments", ["actor_id"])
    op.create_index("ix_inventory_adjustments_product_id", "inventory_adjustments", ["product_id"])
    op.create_index("ix_inventory_adjustments_sku", "inventory_adjustments", ["sku"])


def downgrade() -> None:
    op.drop_index("ix_inventory_adjustments_sku", table_name="inventory_adjustments")
    op.drop_index("ix_inventory_adjustments_product_id", table_name="inventory_adjustments")
    op.drop_index("ix_inventory_adjustments_actor_id", table_name="inventory_adjustments")
    op.drop_table("inventory_adjustments")
    op.drop_column("products", "low_stock_threshold")
