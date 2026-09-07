"""Immutable profiles and redacted provider operation evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0006_profiles_providers"
down_revision = "0005_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutor_profile_version",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("administrator.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "version", name="uq_profile_version"),
        sa.CheckConstraint("version >= 1", name="ck_profile_version"),
    )
    op.create_table(
        "provider_probe",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "route_selection",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("routes", sa.JSON(), nullable=False),
    )
    op.create_table(
        "model_call",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(36),
            sa.ForeignKey("submission.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(2048), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # The snapshot is immutable; its source version remains relationally traceable.
    with op.batch_alter_table("practice_session") as batch:
        batch.add_column(sa.Column("profile_version_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_practice_session_profile_version_id",
            "tutor_profile_version",
            ["profile_version_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("practice_session") as batch:
        batch.drop_column("profile_version_id")
    for name in ("model_call", "route_selection", "provider_probe", "tutor_profile_version"):
        op.drop_table(name)
