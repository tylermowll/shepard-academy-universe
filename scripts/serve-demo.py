"""Disposable same-origin API/UI and worker for browser checks or a synthetic demo."""

import argparse
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=4173)
parser.add_argument("--mode", choices=["demo", "private"], default="demo")
args = parser.parse_args()
children: list[subprocess.Popen[bytes]] = []


def stop(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
with tempfile.TemporaryDirectory(prefix="math-tutor-demo-") as temporary:
    os.environ.update(
        DATABASE_URL=f"sqlite+pysqlite:///{temporary}/demo.sqlite3",
        SESSION_SECRET=secrets.token_urlsafe(48),
        APP_PUBLIC_ORIGIN=f"http://127.0.0.1:{args.port}",
        APP_MODE=args.mode,
        APP_AUDIENCE="mixed",
        ALLOW_CLOUD_INFERENCE="false",
    )
    os.environ.pop("PROVIDER_CONFIG", None)
    from alembic import command
    from alembic.config import Config
    from math_tutor.adapters.db.engine import create_default_engine
    from math_tutor.demo import seed

    configuration = Config()
    configuration.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
    command.upgrade(configuration, "head")
    engine = create_default_engine()
    seed(engine)
    engine.dispose()
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "math_tutor.api.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.port),
                    "--no-proxy-headers",
                    "--no-access-log",
                ],
                cwd=ROOT,
            )
        )
        children.append(
            subprocess.Popen([sys.executable, "-m", "math_tutor.worker"], cwd=ROOT)
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise SystemExit("A demo process stopped unexpectedly.")
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
