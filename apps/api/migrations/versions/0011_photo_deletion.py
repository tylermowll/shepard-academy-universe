"""Durable private image cleanup independent of deleted learner/history rows."""

import sqlalchemy as sa
from alembic import op

revision = "0011_photo_deletion"
down_revision = "0010_ai_tutoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_deletion",
        sa.Column("image_key", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(image_key) = 64 AND image_key NOT GLOB '*[^a-f0-9]*'",
            name="ck_photo_deletion_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("photo_deletion")
