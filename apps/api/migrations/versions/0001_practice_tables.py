"""Initial practice tables: practice_session and problem_instance (T01).

Authentication, pairing, attempts, jobs, and provider tables arrive in the
task that first uses them. PracticeSession.learner_id gains its foreign key
in T03 when the learner table lands.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.sqlite import JSON

revision = "0001_practice_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alias", sa.String(64), nullable=False),
        sa.Column("eligibility", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "eligibility IN ('adult', 'minor', 'unknown')", name="ck_learner_eligibility"
        ),
    )
    op.create_table(
        "practice_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner.id", ondelete="CASCADE", name="fk_practice_session_learner"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'completed', 'skipped')",
            name="ck_practice_session_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_practice_session"),
    )
    op.create_table(
        "problem_instance",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("parameters", JSON(), nullable=False),
        sa.Column("problem_text", sa.Text(), nullable=False),
        sa.Column("expected_result", JSON(), nullable=False),
        sa.Column("format_constraints", JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="assigned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('assigned', 'completed', 'skipped')",
            name="ck_problem_instance_status",
        ),
        sa.CheckConstraint("template_version >= 1", name="ck_problem_instance_template_version"),
        sa.CheckConstraint("position >= 0", name="ck_problem_instance_position"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["practice_session.id"],
            name="fk_problem_instance_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_instance"),
        sa.UniqueConstraint("session_id", "position", name="uq_problem_instance_session_position"),
    )


def downgrade() -> None:
    op.drop_table("problem_instance")
    op.drop_table("practice_session")
    op.drop_table("learner")
