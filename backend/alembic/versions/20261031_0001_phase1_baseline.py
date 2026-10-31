"""Phase 1 database baseline; application tables arrive in later phases.

Revision ID: 20261031_0001
Revises:
Create Date: 2026-10-31
"""

from collections.abc import Sequence

revision: str = "20261031_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish a versioned baseline without premature product tables."""


def downgrade() -> None:
    """No schema objects were created by the foundation baseline."""
