"""Append-only photo interpretation revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0007_interpretations"
down_revision = "0006_profiles_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interpretation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("transcription", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.String(128)),
        sa.Column("ambiguities", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("submission_id", "version", name="uq_interpretation_version"),
        sa.CheckConstraint("version >= 1", name="ck_interpretation_version"),
    )


def downgrade() -> None:
    op.drop_table("interpretation")
