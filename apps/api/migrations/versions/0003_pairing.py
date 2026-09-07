"""Browser-bound pairing. Learner FKs are in the corrected initial schema (D005)."""

import sqlalchemy as sa
from alembic import op

revision = "0003_pairing"
down_revision = "0002_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pairing_request",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learner.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_pairing_request_token_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_pairing_expiration"),
    )


def downgrade() -> None:
    op.drop_table("pairing_request")
