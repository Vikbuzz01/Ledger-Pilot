"""Preserve all valid alternative split-payment candidates per invoice.

Revision ID: 20261101_0006
Revises: 20261031_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261101_0006"
down_revision: str | None = "20261031_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    exists = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM sys.key_constraints "
                "WHERE name = 'uq_candidate_run_pair' AND type = 'UQ'"
            )
        )
        .first()
    )
    if exists:
        op.drop_constraint("uq_candidate_run_pair", "match_candidates", type_="unique")


def downgrade() -> None:
    # A uniqueness constraint could discard valid alternative splits already persisted.
    # The application must archive/remove those candidates before this constraint can return.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT TOP 1 1 FROM match_candidates "
                "WHERE transaction_id IS NULL GROUP BY run_id, invoice_id HAVING COUNT(*) > 1"
            )
        )
        .first()
    )
    if duplicates:
        raise RuntimeError(
            "Cannot downgrade while alternative split candidates share a run and invoice"
        )
    op.create_unique_constraint(
        "uq_candidate_run_pair",
        "match_candidates",
        ["run_id", "transaction_id", "invoice_id"],
    )
