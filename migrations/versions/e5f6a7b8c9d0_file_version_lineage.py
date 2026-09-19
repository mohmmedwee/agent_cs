"""file version lineage

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-19 13:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("root_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("derived_from", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_foreign_key(
        "fk_files_root_id", "files", "files", ["root_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_files_parent_id",
        "files",
        "files",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_files_derived_from",
        "files",
        "files",
        ["derived_from"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_files_root_id", "files", ["root_id"])
    # Linear chain: one child per parent. Multiple NULL roots remain allowed.
    op.create_unique_constraint("uq_files_parent_id", "files", ["parent_id"])

    # Backfill: each existing row is its own root at version 1.
    op.execute(sa.text("UPDATE files SET root_id = id, version = 1 WHERE root_id IS NULL"))


def downgrade() -> None:
    op.drop_constraint("uq_files_parent_id", "files", type_="unique")
    op.drop_index("ix_files_root_id", table_name="files")
    op.drop_constraint("fk_files_derived_from", "files", type_="foreignkey")
    op.drop_constraint("fk_files_parent_id", "files", type_="foreignkey")
    op.drop_constraint("fk_files_root_id", "files", type_="foreignkey")
    op.drop_column("files", "version")
    op.drop_column("files", "derived_from")
    op.drop_column("files", "parent_id")
    op.drop_column("files", "root_id")
