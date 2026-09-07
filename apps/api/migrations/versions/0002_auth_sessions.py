"""Adult authentication tables: administrator and device_session (T02).

Practice tables stay untouched. ``device_session.learner_id`` gains its
foreign key in T03 when the learner table lands.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_auth_sessions"
down_revision = "0001_practice_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "administrator",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("login_name", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_administrator"),
        sa.UniqueConstraint("login_name", name="uq_administrator_login_name"),
    )
    op.create_table(
        "device_session",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="adult"),
        sa.Column("administrator_id", sa.String(36), nullable=True),
        sa.Column("learner_id", sa.String(36), nullable=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["administrator_id"],
            ["administrator.id"],
            name="fk_device_session_administrator",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_session"),
        sa.UniqueConstraint("token_hash", name="uq_device_session_token_hash"),
        sa.CheckConstraint(
            "(role = 'adult' AND administrator_id IS NOT NULL AND learner_id IS NULL) OR "
            "(role = 'learner' AND administrator_id IS NULL AND learner_id IS NOT NULL)",
            name="ck_device_session_principal",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_device_session_expiration"),
    )


def downgrade() -> None:
    op.drop_table("device_session")
    op.drop_table("administrator")
