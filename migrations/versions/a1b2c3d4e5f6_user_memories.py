"""user_memories

Revision ID: a1b2c3d4e5f6
Revises: 0df05d29c390
Create Date: 2026-09-09 23:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0df05d29c390"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="agent", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
    op.create_index(
        "ix_user_memories_user_updated", "user_memories", ["user_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_memories_user_updated", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_table("user_memories")
