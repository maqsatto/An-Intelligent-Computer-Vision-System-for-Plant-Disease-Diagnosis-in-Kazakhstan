# AgroVision

Android MVP for **An Intelligent Computer Vision System for Plant Disease Diagnosis in Kazakhstan**.

Expo / React Native mobile, FastAPI API, PostgreSQL durable worker and an independent ONNX runtime. **No web UI.**

The current local research bundle was actually trained on admitted PlantVillage and Wheat Leaf Dataset images: **3 crops, 9 source-label classes**. It returns exploratory candidates and always abstains (`inconclusive`). It is **not a validated diagnostic release** and does not establish accuracy in Kazakhstan. Production refuses research/synthetic models; absent validated models return `503 model_unavailable` without creating a job.

## Show the MVP

[Краткая инструкция для демонстрации на русском](docs/development/DEMO_RU.md).

1. Start API, PostgreSQL and worker with the commands below.
2. Use the local Android APK in `artifacts/android/` (build/verification status in [mobile report](docs/development/MOBILE_REPORT.md)), or `pnpm mobile` and a compatible development client.
3. Sign in with an operator-issued development bearer, select a culture, choose/take one leaf photo, preview and send. Upload, queued/running and completed/failed are separate states.
4. Read the research candidates and limitations, open your history, optionally leave feedback. Feedback never rewrites the prediction or becomes ground truth.

A phone must reach the computer's API origin on the same network. The local demo APK embeds its API address at build time; rebuilding is necessary when that address changes. Camera/device testing and emulator testing are recorded separately in the report. Unsent drafts are currently in memory; there is **no persistent offline queue or offline inference**.

## Local setup

Verified environment: Linux, Python **3.12.13**, uv **0.12.1**, Node **26.12.0**, pnpm **11.25.0**, PostgreSQL **17.6**, Expo **55.0.31**, RN **0.83.10**, React **19.2.0**. Python and JS dependencies are locked. GPU training is optional and separate from API verification.

```bash
python3 scripts/setup_local.py       # private ignored .env; never overwrites an existing one
uv sync --frozen
pnpm install --frozen-lockfile
docker compose up -d --wait db
uv run alembic upgrade head
```

`setup_local.py` explicitly selects a development-only synthetic infrastructure demo. Its result is always inconclusive and the app displays the development warning. To select the real locally trained research bundle instead:

```bash
uv run python scripts/use_research_bundle.py artifacts/pilot-joint-efficientnet-b0-seed17
```

Models and datasets are deliberately **not in Git**. On another checkout, follow [ML reproduction](ml/README.md) to acquire the admitted sources and train/export a new bundle; do not fabricate weights or claim model support from the crop names.

Run in two terminals:

```bash
uv run uvicorn agrovision.asgi:app --host 0.0.0.0 --port 8000 --no-access-log
uv run python -m agrovision.assessments.worker
```

On this Linux desktop, `AGRO_API_HOST=0.0.0.0 scripts/start_local.sh` starts/restarts the same local services under per-process-tree memory caps. The script uses a systemd user session. Inspect with `systemctl --user status agrovision-api agrovision-worker`; stop with `systemctl --user stop agrovision-api agrovision-worker`. Avoid starting duplicate manual processes on the same port.

Issue the local demo token without logging it:

```bash
uv run python scripts/dev_token.py --subject demo-user --output /tmp/agrovision-demo-token
```

Paste its value into the development login. It expires after 24 hours and is never committed. Development credentials are refused in production. For production, configure HTTPS OIDC issuer/JWKS/audience and mobile AuthSession client/redirect; actual provider login/refresh/revocation requires provider-specific integration verification. The API checks signature, issuer, audience and expiration; owner comes from the verified subject, never client `user_id`.

Interactive API docs: [localhost:8000/docs](http://127.0.0.1:8000/docs). Runtime modes/capabilities: `/v1/catalog`.

## Checks

```bash
uv run ruff check server tests scripts ml
uv run pytest -q
uv run alembic check
uv run python scripts/export_openapi.py
pnpm generate:client
pnpm typecheck
pnpm test:mobile
pnpm --filter @agrovision/mobile exec expo install --check
pnpm --filter @agrovision/mobile exec expo export --platform android --output-dir dist
```

Tests use a separate local `agrovision_test` database. PostgreSQL role needs permission to create that disposable test database; the local Docker profile provides it. They do not delete the application's `agrovision` database or user photos. CI verifies the same layers and generated-client drift; GPU/data downloads are not required. A passed local run is not a claim that hosted CI or phone QA ran.

Live API + **separate running worker**, using a local admitted sample:

```bash
uv run python scripts/e2e.py 'data/images/D05/wheat_leaf/stripe_rust/lolr(1).JPG' --crop wheat
```

This creates a real owner-scoped research observation, validates image download, waits for the committed result, verifies idempotent replay and denies a second actor. Detailed local reports remain in ignored `runs/`.

## Docker backend profile

`compose.yaml` always offers the bounded PostgreSQL service. The opt-in `backend` profile builds API/worker with shared persistent private photo storage. Stop local API/worker before binding Docker's same port.

```bash
docker compose --profile backend up -d --build --wait
```

For an existing research artifact, explicitly set `AGRO_DOCKER_RESEARCH_BUNDLE_DIR=/app/artifacts/pilot-joint-efficientnet-b0-seed17` in the private `.env`. `AGRO_BIND_ADDRESS=0.0.0.0` allows a local phone to connect; default bind is loopback. Production environment is fail-closed and requires real OIDC settings and a properly restricted DB role; the local container DB role is a development administrator. [Verification report](docs/development/VERIFICATION.md) distinguishes configuration checks from actual container builds/runs.

## Reliability and data boundaries

- Observation/photo stable UUIDs and owner-scoped assessment idempotency survive a lost response; changed semantic body returns 409. Assessment and job commit atomically.
- Claim uses short PostgreSQL transactions and `SKIP LOCKED`. Inference and image/model IO happen outside transaction locks in a supervised bounded subprocess. Reclaim/finalize share observation → assessment → job lock order and compare the current lease token/deadline.
- Default: 3 attempts, 60 s lease, 30 s total predictor budget, bounded exponential backoff. Even death on the final attempt becomes an explicit failure. At-least-once computation, one immutable committed result.
- Private photos: actual JPEG/PNG decode, 10 MiB/20 MP source and4 MP projected resize limits, EXIF/RGB normalization and stripped metadata. Two upload slots bound image memory; saturation returns 429/Retry-After. Ready image bytes/metadata and terminal assessment inputs/results are guarded in PostgreSQL.
- Every personal read/write/download checks ownership and tombstones. A signed download URL still needs the owner's bearer. Upload leases recover interrupted reservations. Cleanup removes tombstoned/abandoned blobs and revisits late/orphan writes without unbounded directory buffering.
- User images are not automatically training data. No datasets, weights, private photos, credentials or signing keys go into Git.

## Documents and next increment

- [Measured model cases and paired comparison](docs/evaluation/MEASURED_CASES.md).
- [Measured data/model report](docs/development/DATA_AND_MODEL.md), [mobile report](docs/development/MOBILE_REPORT.md), [verification](docs/development/VERIFICATION.md).
- [Foundation](docs/foundation/README.md), [API contract](docs/foundation/contracts/API_CONTRACT.md), [implementation decisions](docs/development/IMPLEMENTATION.md).

Next bounded increment: durable offline capture/upload queue (persistent app files + SQLite), restart/reconnect/account-switch tests. Then evaluated model/policy admission, independent external/local assessment, reviewed annotation/feedback workflow, localization, and only later the web client.
