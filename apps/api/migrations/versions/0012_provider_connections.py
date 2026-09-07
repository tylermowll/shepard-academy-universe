"""Private administrator-managed provider connections and explicit routing policy."""

import sqlalchemy as sa
from alembic import op

revision = "0012_provider_connections"
down_revision = "0011_photo_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connection",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("credential_revision", sa.String(36), nullable=False),
    )
    op.create_table(
        "provider_policy",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("allow_cloud_inference", sa.Boolean(), nullable=False),
        sa.Column("app_audience", sa.String(16), nullable=False),
        sa.CheckConstraint("name = 'active'", name="ck_provider_policy_name"),
        sa.CheckConstraint(
            "app_audience IN ('adult_only', 'mixed')", name="ck_provider_policy_audience"
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_policy")
    op.drop_table("provider_connection")
