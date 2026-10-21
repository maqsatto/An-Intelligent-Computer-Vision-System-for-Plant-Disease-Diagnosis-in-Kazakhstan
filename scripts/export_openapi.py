"""Export actual application OpenAPI without connecting to DB or enabling a model."""

import json
from pathlib import Path

from agrovision.app import create_app
from agrovision.config import Settings

settings = Settings(
    _env_file=None,
    environment="test",
    dev_token_secret="schema-export-not-a-credential-" * 2,
    download_secret="schema-export-not-a-credential-" * 2,
)
path = Path("packages/api-client/openapi.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(create_app(settings).openapi(), ensure_ascii=False, indent=2) + "\n")
print(f"Exported {path}")
