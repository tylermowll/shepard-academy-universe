"""Record selected reasoning effort without storing model reasoning or learner text."""

import sqlalchemy as sa
from alembic import op

revision = "0016_reasoning_effort"
down_revision = "0015_normalized_jpeg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("model_call", "provider_probe_result"):
        op.add_column(
            table,
            sa.Column("reasoning_effort", sa.String(16), nullable=False, server_default="default"),
        )


def downgrade() -> None:
    for table in ("model_call", "provider_probe_result"):
        op.drop_column(table, "reasoning_effort")
