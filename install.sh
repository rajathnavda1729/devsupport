#!/usr/bin/env bash
# Thin wrapper kept for compatibility — the devkit CLI does the work (plan → review → apply).
#   ./install.sh <target-repo> [--specs-dir docs/specs] [--dry-run] [--yes] [--force]
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:?usage: install.sh <target-repo> [devkit install options]}"; shift
exec python3 "$SRC/bin/devkit" install --target "$TARGET" "$@"
