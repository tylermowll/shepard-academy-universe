"""Use one bounded metadata-free JPEG format for real photo provider requests."""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0015_normalized_jpeg"
down_revision = "0014_probe_results"
branch_labels = None
depends_on = None


def replace_image_types(types: list[str]) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, configuration FROM provider_connection")
    ).mappings()
    for row in rows:
        raw = row["configuration"]
        configuration: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
        capabilities = configuration.get("capabilities")
        if not isinstance(capabilities, dict):
            continue
        capabilities["accepted_image_mime_types"] = types
        connection.execute(
            sa.text("UPDATE provider_connection SET configuration = :configuration WHERE id = :id"),
            {"configuration": json.dumps(configuration), "id": row["id"]},
        )


def upgrade() -> None:
    replace_image_types(["image/jpeg"])
    # Image probes made before this wire-format cutover no longer establish
    # readiness for the bytes the application will actually send.
    op.execute(sa.text("DELETE FROM provider_probe"))


def downgrade() -> None:
    replace_image_types(["image/png"])
    op.execute(sa.text("DELETE FROM provider_probe"))
