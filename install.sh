#!/usr/bin/env bash
# Install LiftOff. Prefers uv, falls back to pipx, then pip --user.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

if command -v uv >/dev/null 2>&1; then
    echo "› Installing LiftOff with uv…"
    uv tool install --force .
    echo "✓ Done — run:  liftoff"
elif command -v pipx >/dev/null 2>&1; then
    echo "› Installing LiftOff with pipx…"
    pipx install --force .
    echo "✓ Done — run:  liftoff"
else
    echo "› uv/pipx not found; installing with pip (--user)…"
    python3 -m pip install --user --upgrade .
    echo "✓ Done — make sure ~/.local/bin is on your PATH, then run:  liftoff"
fi
