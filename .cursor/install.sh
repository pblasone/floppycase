#!/usr/bin/env bash
# Cloud Agent install: set up easyamiga and its prerequisites.
# Idempotent - safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="$HOME/.easyamiga-venv"

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  python3-venv python3-pip curl ca-certificates lhasa

echo "==> Creating Python virtualenv at $VENV"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -e '.[dev]'

echo "==> Exposing 'easyamiga' on PATH"
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV/bin/easyamiga" "$HOME/.local/bin/easyamiga"

echo "==> Installing Amiberry + WHDLoad via easyamiga's own installer"
# Non-fatal: environment build should still succeed if a download hiccups.
"$VENV/bin/easyamiga" install || echo "WARN: easyamiga install reported issues (see above)"
"$VENV/bin/easyamiga" init

echo "==> Done. Run 'easyamiga doctor' to verify."
