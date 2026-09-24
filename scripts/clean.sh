#!/usr/bin/env bash
# Remove everything in this project that can be regenerated.
# Touches nothing outside the project folder.
set -euo pipefail
cd "$(dirname "$0")/.."
before=$(du -sk . | cut -f1)
rm -rf data/ sandbox/clips/ .pytest_cache/
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
if [[ "${1:-}" == "--all" ]]; then rm -rf .venv; fi
after=$(du -sk . | cut -f1)
echo "freed $(( (before - after) / 1024 )) MB  (use --all to also remove .venv; rebuild with: uv sync)"
