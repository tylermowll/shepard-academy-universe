"""Persist multi-subject reading observations and non-grading tutor feedback."""

import sqlalchemy as sa
from alembic import op

revision = "0010_ai_tutoring"
down_revision = "0009_phone_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "practice_session",
        sa.Column(
            "mode",
            sa.String(16),
            sa.CheckConstraint("mode IN ('built_in', 'ai_tutor')", name="ck_session_mode"),
            nullable=False,
            server_default="built_in",
        ),
    )
    op.add_column(
        "practice_session", sa.Column("topic", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "practice_session",
        sa.Column(
            "initiative",
            sa.String(16),
            sa.CheckConstraint(
                "initiative IN ('tutor_led', 'balanced', 'learner_led')",
                name="ck_session_initiative",
            ),
            nullable=False,
            server_default="balanced",
        ),
    )
    op.add_column("interpretation", sa.Column("reading", sa.JSON(), nullable=True))
    op.add_column("tutor_turn", sa.Column("feedback", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tutor_turn", "feedback")
    op.drop_column("interpretation", "reading")
    op.drop_column("practice_session", "initiative")
    op.drop_column("practice_session", "topic")
    op.drop_column("practice_session", "mode")
