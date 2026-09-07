"""Expiring, owner-issued permission for one phone photograph."""

import sqlalchemy as sa
from alembic import op

revision = "0009_phone_upload"
down_revision = "0008_deletion_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phone_upload",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "issuer_id",
            sa.String(36),
            sa.ForeignKey("device_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_id",
            sa.String(36),
            sa.ForeignKey("problem_instance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("issuer_id", "request_key", name="uq_phone_upload_request"),
        sa.CheckConstraint("version >= 1", name="ck_phone_upload_version"),
        sa.CheckConstraint("expires_at > created_at", name="ck_phone_upload_expiration"),
    )


def downgrade() -> None:
    op.drop_table("phone_upload")
