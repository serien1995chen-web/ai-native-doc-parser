"""add unique file hash

Revision ID: 002_unique_file_hash
Revises: 001_initial
Create Date: 2026-08-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002_unique_file_hash"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a unique constraint on files.file_hash."""
    op.create_unique_constraint("uq_files_file_hash", "files", ["file_hash"])


def downgrade() -> None:
    """Remove the unique constraint on files.file_hash."""
    op.drop_constraint("uq_files_file_hash", "files", type_="unique")
