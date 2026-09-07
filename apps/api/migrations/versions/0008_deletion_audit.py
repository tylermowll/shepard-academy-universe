"""Content-free deletion tombstones and audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "0008_deletion_audit"
down_revision = "0007_interpretations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deletion_tombstone",
        sa.Column("learner_id", sa.String(36), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_event")
    op.drop_table("deletion_tombstone")
