#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/setup_local.py
uv sync --frozen
docker compose up -d --wait db
uv run alembic upgrade head
# Per-process-tree memory limits keep one API/worker from crowding the desktop.
for service in agrovision-api agrovision-worker; do
  if systemctl --user is-active --quiet "$service"; then
    systemctl --user restart "$service"
  fi
done
if ! systemctl --user is-active --quiet agrovision-api; then
  systemd-run --user --unit=agrovision-api --collect \
    -p MemoryMax=768M -p MemorySwapMax=256M -p Restart=on-failure -p RestartSec=2s \
    --working-directory="$PWD" "$(command -v uv)" run --frozen uvicorn agrovision.asgi:app \
    --host "${AGRO_API_HOST:-127.0.0.1}" --port 8000 --no-access-log
fi
if ! systemctl --user is-active --quiet agrovision-worker; then
  systemd-run --user --unit=agrovision-worker --collect \
    -p MemoryMax=1G -p MemorySwapMax=256M -p Restart=on-failure -p RestartSec=2s \
    --working-directory="$PWD" "$(command -v uv)" run --frozen python -m agrovision.assessments.worker
fi
printf 'API/worker started. Local docs: http://127.0.0.1:8000/docs\n'
printf 'For a physical phone set AGRO_API_HOST=0.0.0.0 before first start; use your LAN IP.\n'
