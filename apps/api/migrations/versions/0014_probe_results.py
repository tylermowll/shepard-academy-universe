"""Retain content-free connection-test outcomes for adult troubleshooting."""

import sqlalchemy as sa
from alembic import op

revision = "0014_probe_results"
down_revision = "0013_local_password_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_probe_result",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("step", sa.String(16), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("completion_reason", sa.String(32), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("output_limit", sa.Integer(), nullable=False),
        sa.Column("requests_started", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_provider_probe_result_provider_id", "provider_probe_result", ["provider_id"]
    )


def downgrade() -> None:
    op.drop_table("provider_probe_result")
