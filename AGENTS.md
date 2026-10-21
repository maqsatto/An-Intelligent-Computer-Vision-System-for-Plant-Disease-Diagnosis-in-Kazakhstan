# AgroVision repository

- Current client is Android React Native/Expo. Do not add a web UI or persistent offline queue to the online MVP without a scoped follow-up.
- Read README.md, docs/development/IMPLEMENTATION.md, docs/foundation/contracts/API_CONTRACT.md and the current measured reports before changing behavior. Foundation examples are synthetic design references.
- One owner changes Pydantic/OpenAPI and migrations together. Generate TypeScript with `uv run python scripts/export_openapi.py && pnpm generate:client`; do not hand-edit schema.d.ts.
- API and separate worker share PostgreSQL. Preserve atomic assessment/job creation, owner-scoped idempotency, full model pins, observation→assessment→job locks, short claims and lease fencing.
- Keep runtime free of FastAPI/ORM/training dependencies. Research always abstains; production refuses unvalidated/synthetic bundles. Preserve global scores without crop renormalization.
- Images, datasets, model weights, credentials, signing keys and run outputs stay outside Git. Normalized ready photos and terminal results are immutable.
- Use uv.lock and pnpm-lock.yaml. Verification requires the dedicated local PostgreSQL test database; GPU/data download is not required for API tests.
- Heavy training/build/emulator jobs must be serialized and resource bounded. Keep at least3GiB host RAM available; Android cold native compilation needs the guarded4GiB budget and limited compiler parallelism, not a low reclaim threshold that thrashes swap.
- Split commits by the responsibility ownership explicitly requested by the user (docs/development/GIT_PROFILES.md); preserve the global Git profile. Never invent YouTrack IDs or rewrite shared history.
