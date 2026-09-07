"""Foreground native supervisor; does not read configuration files or migrate data."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from math_tutor import settings

settings.session_secret()
origin = urlsplit(settings.app_public_origin())
if origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit(
        "For HTTPS deployments use the service/gateway runbook; make dev is loopback only."
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
            origin.hostname,
            "--port",
            str(origin.port or 80),
            "--no-proxy-headers",
            "--no-access-log",
        ],
        [sys.executable, "-m", "math_tutor.worker"],
    ):
        children.append(subprocess.Popen(command, cwd=root, env=os.environ.copy()))
    print(
        f"Math Practice Tutor: {origin.geturl()} (Ctrl+C stops API and worker)",
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
