"""add order fulfillment fields

Revision ID: 20260801_0006
Revises: 20260801_0005
Create Date: 2026-08-01 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0006"
down_revision: str | None = "20260801_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("note", sa.String(length=500), nullable=False, server_default=""),
    )
    op.add_column(
        "orders",
        sa.Column("shipping_carrier", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "orders",
        sa.Column("tracking_number", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("orders", "note", server_default=None)
    op.alter_column("orders", "shipping_carrier", server_default=None)
    op.alter_column("orders", "tracking_number", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "shipped_at")
    op.drop_column("orders", "tracking_number")
    op.drop_column("orders", "shipping_carrier")
    op.drop_column("orders", "note")
