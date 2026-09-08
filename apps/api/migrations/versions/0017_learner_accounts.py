"""Preserve learner histories while adding unique, administrator-managed sign-ins."""

import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0017_learner_accounts"
down_revision = "0016_reasoning_effort"
branch_labels = None
depends_on = None


def normalized(value: str) -> str:
    # Keep the historical migration independent of future application validators.
    cleaned = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    return " ".join(unicodedata.normalize("NFKC", cleaned).split())[:64] or "Learner"


def upgrade() -> None:
    op.add_column(
        "learner", sa.Column("alias_key", sa.String(256), nullable=False, server_default="")
    )
    op.add_column("learner", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "learner",
        sa.Column("local_only_password", sa.Boolean(), nullable=False, server_default="0"),
    )
    connection = op.get_bind()
    reserved = {
        normalized(name).casefold()
        for name in connection.execute(sa.text("SELECT login_name FROM administrator")).scalars()
    }
    for row in (
        connection.execute(
            sa.text("SELECT id, alias, deleted_at FROM learner ORDER BY created_at, id")
        )
        .mappings()
        .all()
    ):
        base = normalized(row["alias"])
        name, number = base, 2
        if row["deleted_at"] is None:
            while name.casefold() in reserved:
                suffix = f" ({number})"
                name = base[: 64 - len(suffix)] + suffix
                number += 1
            reserved.add(name.casefold())
        connection.execute(
            sa.text("UPDATE learner SET alias=:name, alias_key=:key WHERE id=:id"),
            {"name": name, "key": name.casefold(), "id": row["id"]},
        )
    op.create_index(
        "uq_learner_alias_key",
        "learner",
        ["alias_key"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("pairing_request")


def downgrade() -> None:
    op.create_table(
        "pairing_request",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("learner_id", sa.String(36), sa.ForeignKey("learner.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at", name="ck_pairing_expiration"),
        sa.UniqueConstraint("token_hash", name="uq_pairing_request_token_hash"),
    )
    op.drop_index("uq_learner_alias_key", table_name="learner")
    op.drop_column("learner", "local_only_password")
    op.drop_column("learner", "password_hash")
    op.drop_column("learner", "alias_key")
