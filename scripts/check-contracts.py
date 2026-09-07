"""Regenerate contracts into temporary files and reject any committed drift."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="math-contract-drift-") as temporary:
    schema = Path(temporary) / "openapi.json"
    client = Path(temporary) / "api.d.ts"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/export-contracts.py"),
            "--output",
            str(schema),
        ],
        check=True,
        cwd=root,
    )
    subprocess.run(
        [
            "pnpm",
            "--filter",
            "@math-tutor/contracts",
            "exec",
            "openapi-typescript",
            str(schema),
            "-o",
            str(client),
        ],
        check=True,
        cwd=root,
        env=os.environ.copy(),
    )
    subprocess.run(
        ["pnpm", "exec", "prettier", "--write", str(client)], check=True, cwd=root
    )
    for expected, generated in (
        (root / "contracts/openapi.json", schema),
        (root / "apps/web/src/generated/api.d.ts", client),
    ):
        if expected.read_bytes() != generated.read_bytes():
            raise SystemExit(
                f"Generated contract drift: {expected.relative_to(root)}. Run make contracts."
            )
