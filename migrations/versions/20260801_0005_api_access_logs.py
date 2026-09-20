"""add api access logs

Revision ID: 20260801_0005
Revises: 20260801_0004
Create Date: 2026-08-01 02:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0005"
down_revision: str | None = "20260801_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_access_logs_api_key_id", "api_access_logs", ["api_key_id"])
    op.create_index("ix_api_access_logs_key_prefix", "api_access_logs", ["key_prefix"])
    op.create_index("ix_api_access_logs_path", "api_access_logs", ["path"])
    op.create_index("ix_api_access_logs_status", "api_access_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_api_access_logs_status", table_name="api_access_logs")
    op.drop_index("ix_api_access_logs_path", table_name="api_access_logs")
    op.drop_index("ix_api_access_logs_key_prefix", table_name="api_access_logs")
    op.drop_index("ix_api_access_logs_api_key_id", table_name="api_access_logs")
    op.drop_table("api_access_logs")
