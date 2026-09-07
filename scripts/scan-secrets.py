"""Scan tracked public text for common token/private-key formats without printing matches."""

import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = (
    subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
)
patterns = [
    re.compile(value)
    for value in (
        r"AKIA[A-Z0-9]{16}",
        r"gh[pousr]_[A-Za-z0-9]{30,}",
        r"github_pat_[A-Za-z0-9_]{40,}",
        r"sk-[A-Za-z0-9_-]{32,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
]
failed = []
for name in paths:
    if not name:
        continue
    path = root / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
        continue
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    if any(pattern.search(text) for pattern in patterns):
        failed.append(name)
if failed:
    raise SystemExit("Potential credential material in: " + ", ".join(failed))
print("Tracked public text credential scan passed.")
