"""conversation branching lineage

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-17 00:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("branched_at_position", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_parent_id",
        "conversations",
        "conversations",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_parent_id",
        "conversations",
        ["parent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_parent_id", table_name="conversations")
    op.drop_constraint("fk_conversations_parent_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "branched_at_position")
    op.drop_column("conversations", "parent_id")
