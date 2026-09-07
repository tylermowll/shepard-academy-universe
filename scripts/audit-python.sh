#!/bin/sh
set -eu
requirements_file=$(mktemp /tmp/math-tutor-audit-XXXXXX.txt)
trap 'rm -f "$requirements_file"' EXIT HUP INT TERM
uv export --directory apps/api --locked --format requirements-txt --no-emit-project --output-file "$requirements_file" >/dev/null
uv run --directory apps/api --locked pip-audit --disable-pip --require-hashes -r "$requirements_file"
