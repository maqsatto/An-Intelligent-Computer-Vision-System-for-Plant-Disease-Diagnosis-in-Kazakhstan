#!/usr/bin/env bash
# Start the AgroVision KZ web demo (no database, no Docker): http://127.0.0.1:8080
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f webapp/models/active/manifest.json ] || { echo "Model bundle missing: see docs/development/WEB_DEMO_RU.md" >&2; exit 1; }
uv sync --frozen
exec uv run --frozen uvicorn webapp.app:app --host "${AGRO_WEB_HOST:-127.0.0.1}" --port "${AGRO_WEB_PORT:-8080}" --no-access-log
