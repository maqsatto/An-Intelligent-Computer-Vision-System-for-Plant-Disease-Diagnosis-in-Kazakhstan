"""Create ignored local credentials without overwriting existing settings."""
from pathlib import Path
import secrets

path = Path('.env')
if path.exists():
    print('.env exists; preserved')
else:
    password = secrets.token_urlsafe(24)
    path.write_text(
        f'POSTGRES_PASSWORD={password}\n'
        f'AGRO_DATABASE_URL=postgresql+psycopg://agrovision:{password}@127.0.0.1:55432/agrovision\n'
        'AGRO_ENVIRONMENT=development\nAGRO_DEV_PREDICTOR=true\n'
        f'AGRO_DEV_TOKEN_SECRET={secrets.token_urlsafe(48)}\n'
        f'AGRO_DOWNLOAD_SECRET={secrets.token_urlsafe(48)}\n'
        'AGRO_STORAGE_DIR=storage/photos\nAGRO_BUNDLE_DIR=artifacts/active\n'
    )
    path.chmod(0o600)
    print('Created private .env (development only)')
