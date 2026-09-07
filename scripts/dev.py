"""Foreground native supervisor; does not read configuration files or migrate data."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from math_tutor import settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--gateway",
    action="store_true",
    help="Serve on loopback port 8000 behind a separately configured HTTPS gateway.",
)
args = parser.parse_args()
settings.session_secret()
origin = urlsplit(settings.app_public_origin())
if args.gateway and origin.scheme != "https":
    raise SystemExit(
        "make serve requires APP_PUBLIC_ORIGIN=https://your-phone-reachable-hostname (see docs/PHONE_SETUP.md)."
    )
if not args.gateway and (
    origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
):
    raise SystemExit(
        "For HTTPS deployments use make serve behind the gateway; make dev is loopback only."
    )
root = Path(__file__).resolve().parents[1]
children = []


def stop(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
try:
    for command in (
        [
            sys.executable,
            "-m",
            "uvicorn",
            "math_tutor.api.app:app",
            "--host",
            "127.0.0.1" if args.gateway else origin.hostname,
            "--port",
            "8000" if args.gateway else str(origin.port or 80),
            "--no-proxy-headers",
            "--no-access-log",
        ],
        [sys.executable, "-m", "math_tutor.worker"],
    ):
        children.append(subprocess.Popen(command, cwd=root, env=os.environ.copy()))
    print(
        f"Shepard Tutor: {origin.geturl()} (Ctrl+C stops API and worker)",
        flush=True,
    )
    while all(child.poll() is None for child in children):
        time.sleep(0.5)
    raise SystemExit("A service exited; inspect its safe error and restart.")
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
