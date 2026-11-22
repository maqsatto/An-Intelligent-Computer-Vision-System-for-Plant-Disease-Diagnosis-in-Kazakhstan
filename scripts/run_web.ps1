# Start the AgroVision KZ web demo (no database, no Docker): http://127.0.0.1:8080
param([int]$Port = 8080, [string]$Bind = "127.0.0.1")
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "webapp/models/active/manifest.json")) {
  Write-Error "Model bundle not found: copy it to webapp/models/active (see docs/development/WEB_DEMO_RU.md)."
  exit 1
}
uv sync --frozen
uv run --frozen uvicorn webapp.app:app --host $Bind --port $Port --no-access-log
