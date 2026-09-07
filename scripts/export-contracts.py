"""Export OpenAPI without opening an operator database or provider settings."""

import argparse
import json
import os
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="math-tutor-contracts-") as temp:
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{temp}/contracts.sqlite3"
    os.environ.pop("PROVIDER_CONFIG", None)
    from math_tutor.api.app import create_app

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    )
