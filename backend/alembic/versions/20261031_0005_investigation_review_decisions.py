"""Ensure approval decisions can target either match or investigation.

Revision ID: 20261031_0005
Revises: 20261031_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "20261031_0005"
down_revision: str | None = "20261031_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {item["name"]: item for item in inspector.get_columns("approval_decisions")}
    if "investigation_id" not in columns:
        op.add_column(
            "approval_decisions",
            sa.Column("investigation_id", sa.Uuid(as_uuid=True), nullable=True),
        )
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("approval_decisions")}
    fk_name = "fk_approval_decisions_investigation_id_investigations"
    if fk_name not in foreign_keys:
        op.create_foreign_key(
            fk_name, "approval_decisions", "investigations", ["investigation_id"], ["id"]
        )
    if "review_target_key" not in columns:
        op.add_column(
            "approval_decisions", sa.Column("review_target_key", sa.String(80), nullable=True)
        )
    table = sa.table(
        "approval_decisions",
        sa.column("candidate_id", sa.Uuid(as_uuid=True)),
        sa.column("review_target_key", sa.String(80)),
    )
    for row in bind.execute(
        sa.select(table.c.candidate_id).where(table.c.review_target_key.is_(None))
    ):
        if row.candidate_id is None:
            raise RuntimeError("Cannot backfill an approval decision without a candidate")
        bind.execute(
            table.update()
            .where(table.c.candidate_id == row.candidate_id)
            .values(review_target_key=f"candidate:{row.candidate_id}")
        )
    if not columns.get("candidate_id", {}).get("nullable", True):
        op.alter_column("approval_decisions", "candidate_id", nullable=True)
    if columns.get("review_target_key", {}).get("nullable", True):
        op.alter_column("approval_decisions", "review_target_key", nullable=False)
    indexes = {item["name"] for item in inspector.get_indexes("approval_decisions")}
    if "uq_approval_review_target" not in indexes:
        op.create_unique_constraint(
            "uq_approval_review_target", "approval_decisions", ["business_id", "review_target_key"]
        )
    check_exists = bind.execute(
        sa.text(
            "SELECT 1 FROM sys.check_constraints WHERE name = 'ck_approval_target' "
            "AND parent_object_id = OBJECT_ID('approval_decisions')"
        )
    ).first()
    if not check_exists:
        op.create_check_constraint(
            "ck_approval_target",
            "approval_decisions",
            "(candidate_id IS NOT NULL AND investigation_id IS NULL) OR "
            "(candidate_id IS NULL AND investigation_id IS NOT NULL)",
        )


def downgrade() -> None:
    bind = op.get_bind()
    investigation_decisions = bind.execute(
        sa.text("SELECT TOP 1 1 FROM approval_decisions WHERE investigation_id IS NOT NULL")
    ).first()
    if investigation_decisions:
        raise RuntimeError("Cannot downgrade while human decisions reference AI investigations")
    inspector = inspect(bind)
    checks = bind.execute(
        sa.text(
            "SELECT name FROM sys.check_constraints WHERE parent_object_id = "
            "OBJECT_ID('approval_decisions')"
        )
    )
    if "ck_approval_target" in {row[0] for row in checks}:
        op.drop_constraint("ck_approval_target", "approval_decisions", type_="check")
    indexes = {item["name"] for item in inspector.get_indexes("approval_decisions")}
    if "uq_approval_review_target" in indexes:
        op.drop_constraint("uq_approval_review_target", "approval_decisions", type_="unique")
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("approval_decisions")}
    fk_name = "fk_approval_decisions_investigation_id_investigations"
    if fk_name in foreign_keys:
        op.drop_constraint(fk_name, "approval_decisions", type_="foreignkey")
    columns = {item["name"]: item for item in inspector.get_columns("approval_decisions")}
    if "review_target_key" in columns:
        op.drop_column("approval_decisions", "review_target_key")
    if "investigation_id" in columns:
        op.drop_column("approval_decisions", "investigation_id")
    if columns.get("candidate_id", {}).get("nullable", False):
        op.alter_column("approval_decisions", "candidate_id", nullable=False)
