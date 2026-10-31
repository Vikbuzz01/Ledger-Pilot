"""Deterministic reconciliation, investigation, and approvals.

Revision ID: 20261031_0004
Revises: 20261031_0003
"""

from collections.abc import Sequence

from alembic import op
from app.db.base import Base
from app.modules.reconciliation import models as _models  # noqa: F401

revision: str = "20261031_0004"
down_revision: str | None = "20261031_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    Base.metadata.tables[name]
    for name in (
        "reconciliation_runs",
        "match_candidates",
        "payment_allocations",
        "reconciliation_exceptions",
        "vendor_alias_candidates",
        "investigations",
        "investigation_tool_executions",
        "approval_decisions",
        "audit_events",
    )
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=TABLES, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(TABLES)), checkfirst=True)
