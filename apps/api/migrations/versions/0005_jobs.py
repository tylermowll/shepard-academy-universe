"""Durable operation claims and worker readiness."""

import sqlalchemy as sa
from alembic import op

revision = "0005_jobs"
down_revision = "0004_practice_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("policy_digest", sa.String(64), nullable=False),
        sa.CheckConstraint("attempts BETWEEN 0 AND 6", name="ck_job_attempts"),
        sa.CheckConstraint("call_count BETWEEN 0 AND 6", name="ck_job_calls"),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'completed', 'failed', 'canceled', 'waiting')",
            name="ck_job_state",
        ),
    )
    op.create_table(
        "worker_heartbeat",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat")
    op.drop_table("job")
