"""Container owner command over a private Unix socket; no public issuance route."""

from __future__ import annotations

import os
import socket
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from socketserver import BaseRequestHandler, UnixStreamServer
from threading import Thread

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from math_tutor import auth, settings
from math_tutor.setup_gate import SetupGate

SOCKET_ENV = "SHEPHERD_OWNER_SOCKET"


def owner_response(engine: Engine, gate: SetupGate) -> str:
    """Serialize issuance with account creation; never reset existing credentials."""
    if os.getenv("APP_MODE", "private") == "demo":
        return "Account setup is unavailable in demo mode."
    origin = settings.app_public_origin()
    with Session(engine) as db:
        db.connection(execution_options={"sqlite_begin_immediate": True})
        if not auth.setup_required(db):
            return f"Your app is already running. Sign in at {origin}/"
        token = gate.renew()
    return (
        "Create your administrator account in the browser. This private link replaces "
        "earlier links, works once, and expires in 30 minutes; do not share it:\n"
        f"{origin}/#setup={token}"
    )


@contextmanager
def owner_channel(engine: Engine, gate: SetupGate) -> Iterator[None]:
    """Only the container's OS owner can connect; authority stays in API memory."""
    configured = os.environ.get(SOCKET_ENV)
    if not configured or os.getenv("APP_MODE", "private") == "demo":
        yield
        return
    path = Path(configured)
    if not path.is_absolute():
        raise ValueError("Owner socket must have an absolute path.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise ValueError("Owner socket requires an owner-only directory (permissions 700).")
    # An API restart may leave its socket on tmpfs. Refuse a live listener or
    # non-socket instead of unlinking another process's channel.
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError("Owner socket path is occupied.")
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(2)
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise ValueError("An owner channel is already running.")

    class Handler(BaseRequestHandler):
        def handle(self) -> None:
            self.request.settimeout(2)
            try:
                if self.request.recv(16) != b"setup-link\n":
                    return
                try:
                    response = owner_response(engine, gate)
                except SQLAlchemyError, ValueError:
                    response = "Cannot prepare account setup. Check the app's local configuration."
                self.request.sendall((response + "\n").encode())
            except OSError:
                pass  # Never log request data or owner authority.

    with UnixStreamServer(str(path), Handler) as server:
        path.chmod(0o600)
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            thread.join()
            path.unlink(missing_ok=True)


def main() -> int:
    """Run with docker exec, printing the link only in the operator's terminal."""
    configured = os.environ.get(SOCKET_ENV)
    if not configured:
        print("This API needs the container setup update. Rebuild the app image.", file=sys.stderr)
        return 1
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(10)
            client.connect(configured)
            client.sendall(b"setup-link\n")
            with client.makefile("rb") as response:
                output = response.read(4097)
        if len(output) > 4096 or not output:
            raise ValueError("Invalid owner response")
        print(output.decode(), end="")
        return 0 if "#setup=" in output.decode() or "Sign in at " in output.decode() else 1
    except OSError, ValueError:
        print(
            "Cannot reach account setup. Check that the API container is running.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
