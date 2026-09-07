"""Persist practice requests, immutable attempts, verdicts and assistance."""

import sqlalchemy as sa
from alembic import op

revision = "0004_practice_flow"
down_revision = "0003_pairing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("practice_session") as batch:
        batch.add_column(sa.Column("request_key", sa.String(128), nullable=False))
        batch.add_column(sa.Column("payload_hash", sa.String(64), nullable=False))
        batch.add_column(sa.Column("profile_settings", sa.JSON(), nullable=False))
        batch.create_unique_constraint("uq_session_request", ["learner_id", "request_key"])
    with op.batch_alter_table("problem_instance") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("assistance_level", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("request_key", sa.String(128), nullable=False))
    op.create_table(
        "submission",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_id",
            sa.String(36),
            sa.ForeignKey("problem_instance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("work_text", sa.Text(), nullable=False),
        sa.Column("help_level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("safe_error", sa.String(256)),
        sa.Column("image_key", sa.String(64)),
        sa.Column("assignment_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("learner_id", "request_key", name="uq_submission_request"),
        sa.CheckConstraint("kind IN ('answer', 'question', 'hint')", name="ck_submission_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'checking', 'tutoring', 'interpreting', 'awaiting_confirmation', 'completed', 'failed', 'canceled')",
            name="ck_submission_status",
        ),
        sa.CheckConstraint("help_level BETWEEN 0 AND 4", name="ck_submission_help"),
    )
    op.create_table(
        "evaluation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("answer_status", sa.String(32), nullable=False),
        sa.Column("format_status", sa.String(32), nullable=False),
        sa.Column("reasoning_status", sa.String(32), nullable=False),
        sa.Column("verifier_version", sa.String(32), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False),
    )
    op.create_table(
        "tutor_turn",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("assistance_level", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "progress_event",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("assistance_level", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for name in ("progress_event", "tutor_turn", "evaluation", "submission"):
        op.drop_table(name)
    with op.batch_alter_table("problem_instance") as batch:
        for name in ("request_key", "assistance_level", "version"):
            batch.drop_column(name)
    with op.batch_alter_table("practice_session") as batch:
        batch.drop_constraint("uq_session_request", type_="unique")
        for name in ("request_key", "payload_hash", "profile_settings"):
            batch.drop_column(name)
