"""Constrain session identity and lifetime after the T02 review.

Preserve existing valid sessions and named foreign/unique constraints. Invalid
legacy rows cause the migration to roll back for operator review, never silent
deletion or reassignment. Application writes must be stopped for this rebuild.
"""

from alembic import op

revision = "0003_session_invariants"
down_revision = "0002_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("device_session") as batch:
        batch.create_check_constraint(
            "ck_device_session_principal",
            "(role = 'adult' AND administrator_id IS NOT NULL AND learner_id IS NULL) OR "
            "(role = 'learner' AND administrator_id IS NULL AND learner_id IS NOT NULL)",
        )
        batch.create_check_constraint("ck_device_session_expiration", "expires_at > created_at")
    if op.get_bind().exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Foreign-key validation failed after rebuilding device_session.")


def downgrade() -> None:
    with op.batch_alter_table("device_session") as batch:
        batch.drop_constraint("ck_device_session_expiration", type_="check")
        batch.drop_constraint("ck_device_session_principal", type_="check")
