"""Explicit operator transfer of an encrypted backup; never activated by learner requests."""

import argparse
import os
from pathlib import Path
from uuid import UUID

from math_tutor.adapters.cloud_storage import S3Storage
from math_tutor.backup import MAGIC


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicit private S3 transfer of an encrypted archive."
    )
    parser.add_argument("action", choices=["put", "get", "delete"])
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--key", type=UUID, required=True)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    store = S3Storage(args.bucket, args.region, prefix="backups")
    try:
        if args.action == "delete":
            store.delete(args.key)
        elif args.action == "put":
            if args.file is None or args.file.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Select an encrypted archive under 64 MiB.")
            data = args.file.read_bytes()
            if not data.startswith(MAGIC):
                raise ValueError("Only encrypted tutor archives may be uploaded.")
            store.put(args.key, data)
        else:
            if args.file is None:
                raise ValueError("Select a new destination file.")
            data = store.get(args.key)
            if not data.startswith(MAGIC):
                raise ValueError("Remote object is not an encrypted tutor archive.")
            descriptor = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
    finally:
        store.close()
    print("Private encrypted archive transfer completed.")


if __name__ == "__main__":
    main()
