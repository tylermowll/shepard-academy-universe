"""Reconnect the standard local Docker installation before starting native services."""

import shutil
import subprocess


def running_api() -> str | None:
    """Inspect public container metadata only, never container settings or logs."""
    if shutil.which("docker") is None:
        return None
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "publish=8000",
                "--filter",
                "label=com.docker.compose.service=api",
                "--format",
                "{{.ID}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode:
            return None
        candidates = [
            value
            for value in result.stdout.splitlines()
            if value and all(character in "0123456789abcdef" for character in value)
        ]
        if not candidates:
            return None
        # `docker ps .Image` becomes an image ID when a build moves the tag.
        # Config.Image retains the launch reference. Read only that public
        # field, never Config.Env or the rest of the container configuration.
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}} {{.Config.Image}}", *candidates],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if result.returncode:
        return None
    matches = [
        parts[0]
        for line in result.stdout.splitlines()
        if len(parts := line.split()) == 2
        and parts[1] == "math-practice-tutor:local"
        and all(character in "0123456789abcdef" for character in parts[0])
    ]
    return matches[0] if len(matches) == 1 else None


def connect(container: str) -> int:
    print("The tutor is already running in Docker. Connecting to account setup…", flush=True)
    result = subprocess.run(
        ["docker", "exec", container, "python", "-m", "math_tutor.owner_setup"],
        check=False,
    )
    if result.returncode:
        print(
            "Could not connect to Docker account setup. The API must use the current "
            "image and Compose configuration. See the container section of docs/RUNBOOK.md."
        )
    return result.returncode
