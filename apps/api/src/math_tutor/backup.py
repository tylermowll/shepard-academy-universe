"""Encrypted, consistent SQLite bundles restored only into a new private directory."""

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import warnings
import zipfile
from contextlib import closing
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from math_tutor import settings

MAGIC = b"MTPBACK1"
CHUNK = 1024 * 1024


def key_for(password: str, salt: bytes) -> bytes:
    if len(password) < 12:
        raise ValueError("Use a backup passphrase of at least 12 characters.")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def encrypt(source: Path, destination: Path, password: str) -> None:
    salt, nonce = os.urandom(16), os.urandom(12)
    cipher = Cipher(algorithms.AES(key_for(password, salt)), modes.GCM(nonce)).encryptor()
    header = MAGIC + salt + nonce
    cipher.authenticate_additional_data(header)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with source.open("rb") as incoming, os.fdopen(descriptor, "wb") as outgoing:
            outgoing.write(header)
            while data := incoming.read(CHUNK):
                outgoing.write(cipher.update(data))
            outgoing.write(cipher.finalize())
            outgoing.write(cipher.tag)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def decrypt(source: Path, destination: Path, password: str) -> None:
    if source.stat().st_size > 2 * 1024**3:
        raise ValueError("Backup exceeds the supported 2 GiB bundle limit.")
    with source.open("rb") as incoming:
        header = incoming.read(36)
        if header[:8] != MAGIC:
            raise ValueError("Unknown backup format.")
        incoming.seek(-16, 2)
        tag = incoming.read(16)
        cipher = Cipher(
            algorithms.AES(key_for(password, header[8:24])), modes.GCM(header[24:36], tag)
        ).decryptor()
        cipher.authenticate_additional_data(header)
        incoming.seek(36)
        remaining = source.stat().st_size - 52
        with destination.open("xb") as outgoing:
            destination.chmod(0o600)
            while remaining > 0:
                block = incoming.read(min(CHUNK, remaining))
                if not block:
                    raise ValueError("Truncated backup.")
                outgoing.write(cipher.update(block))
                remaining -= len(block)
            outgoing.write(cipher.finalize())


def check_database(connection: sqlite3.Connection) -> None:
    if (
        connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
        or connection.execute("PRAGMA foreign_key_check").fetchall()
    ):
        raise ValueError("Backup database failed integrity validation.")


def file_hash(path: Path) -> str:
    with path.open("rb") as incoming:
        return hashlib.file_digest(incoming, "sha256").hexdigest()


def backup(destination: Path, password: str) -> None:
    source = settings.database_path()
    if not source.is_file():
        raise ValueError("Configured database does not exist.")
    with tempfile.TemporaryDirectory(prefix="math-backup-") as temporary:
        root = Path(temporary)
        snapshot = root / "db.sqlite3"
        with (
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as db,
            sqlite3.connect(snapshot) as target,
        ):
            db.backup(target)
            check_database(target)
            keys = [
                row[0]
                for row in target.execute(
                    "SELECT image_key FROM submission WHERE image_key IS NOT NULL"
                )
            ]
            revision = target.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        files = {"db.sqlite3": snapshot}
        ledger = source.parent / "deletions.jsonl"
        if ledger.exists():
            files["deletions.jsonl"] = ledger
        for key in keys:
            if re.fullmatch(r"[a-f0-9]{64}", key) is None:
                raise ValueError("Invalid retained object key.")
            path = source.parent / "objects" / key
            if path.is_symlink() or not path.is_file():
                raise ValueError(
                    "Retained object is unavailable. Finish retention cleanup before backup."
                )
            files["objects/" + key] = path
        manifest = {
            "schema_revision": revision,
            "sha256": {name: file_hash(path) for name, path in files.items()},
        }
        archive = root / "bundle.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, path in files.items():
                bundle.write(path, name)
            bundle.writestr("manifest.json", json.dumps(manifest))
        encrypt(archive, destination, password)


def restore(source: Path, destination: Path, password: str, current_ledger: Path) -> None:
    if destination.exists():
        raise ValueError("Restore destination must be a new directory.")
    # Require the current ledger even when empty; old backups cannot supply later deletions.
    tombstones = {str(UUID(line)) for line in current_ledger.read_text().splitlines() if line}
    with tempfile.TemporaryDirectory(prefix="math-restore-") as temporary:
        root = Path(temporary)
        archive = root / "bundle.zip"
        decrypt(source, archive, password)
        extracted = root / "verified"
        extracted.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 2 * 1024**3:
                raise ValueError("Backup contents exceed restore limits.")
            seen: set[str] = set()
            for entry in entries:
                name = entry.filename
                if name in seen or (
                    name not in {"manifest.json", "db.sqlite3", "deletions.jsonl"}
                    and re.fullmatch(r"objects/[a-f0-9]{64}", name) is None
                ):
                    raise ValueError("Unsafe backup member.")
                seen.add(name)
                path = extracted / name
                path.parent.mkdir(mode=0o700, exist_ok=True)
                with bundle.open(entry) as incoming, path.open("xb") as outgoing:
                    path.chmod(0o600)
                    shutil.copyfileobj(incoming, outgoing, CHUNK)
        manifest = json.loads((extracted / "manifest.json").read_text())
        if set(manifest["sha256"]) != seen - {"manifest.json"}:
            raise ValueError("Backup manifest does not match its files.")
        for name, expected in manifest["sha256"].items():
            with (extracted / name).open("rb") as incoming:
                if hashlib.file_digest(incoming, "sha256").hexdigest() != expected:
                    raise ValueError("Backup content checksum mismatch.")
        old_ledger = extracted / "deletions.jsonl"
        if old_ledger.exists():
            tombstones.update(
                str(UUID(line)) for line in old_ledger.read_text().splitlines() if line
            )
        with closing(sqlite3.connect(extracted / "db.sqlite3")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            check_database(db)
            for learner_id in tombstones:
                for (key,) in db.execute(
                    "SELECT image_key FROM submission WHERE learner_id=? AND image_key IS NOT NULL",
                    (learner_id,),
                ):
                    (extracted / "objects" / key).unlink(missing_ok=True)
                db.execute("DELETE FROM learner WHERE id=?", (learner_id,))
                db.execute(
                    "INSERT OR IGNORE INTO deletion_tombstone(learner_id,deleted_at) VALUES (?,datetime('now'))",
                    (learner_id,),
                )
            # Restored credentials never resurrect authenticated browser sessions or in-flight work.
            db.execute("DELETE FROM device_session")
            db.execute("DELETE FROM pairing_request")
            db.execute(
                "UPDATE job SET state='canceled',lease_token=NULL WHERE state NOT IN ('completed','canceled')"
            )
            db.execute(
                "UPDATE submission SET status='canceled' WHERE status NOT IN ('completed','canceled')"
            )
            db.commit()
            check_database(db)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        (extracted / "deletions.jsonl").write_text(
            "".join(value + "\n" for value in sorted(tombstones))
        )
        destination.mkdir(mode=0o700)
        try:
            for path in extracted.iterdir():
                if path.name == "manifest.json":
                    continue
                target = destination / (
                    "math_tutor.sqlite3" if path.name == "db.sqlite3" else path.name
                )
                if path.is_dir():
                    shutil.copytree(path, target)
                else:
                    shutil.copyfile(path, target)
                    target.chmod(0o600)
        except Exception:
            shutil.rmtree(destination)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypted backup/restore with writes stopped.")
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--deletion-ledger", type=Path)
    parser.add_argument("--writes-stopped", action="store_true", required=True)
    args = parser.parse_args()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Backup passphrase (never stored): ")
    if args.action == "backup":
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            confirmation = getpass.getpass("Confirm passphrase: ")
        if password != confirmation:
            raise SystemExit("Passphrases do not match.")
        backup(args.path, password)
    else:
        if args.destination is None or args.deletion_ledger is None:
            raise SystemExit("Restore requires --destination and the current --deletion-ledger.")
        restore(args.path, args.destination, password, args.deletion_ledger)
    print("Encrypted backup operation completed. Configuration secrets are managed separately.")


if __name__ == "__main__":
    main()
