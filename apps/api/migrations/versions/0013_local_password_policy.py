"""Remember accounts that require a password reset before network access."""

import sqlalchemy as sa
from alembic import op

revision = "0013_local_password_policy"
down_revision = "0012_provider_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "administrator",
        sa.Column("local_only_password", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .exec_driver_sql("SELECT 1 FROM administrator WHERE local_only_password = 1 LIMIT 1")
        .first()
        is not None
    ):
        raise RuntimeError(
            "Reset local-only administrator passwords to at least 12 characters before downgrading this schema."
        )
    op.drop_column("administrator", "local_only_password")
