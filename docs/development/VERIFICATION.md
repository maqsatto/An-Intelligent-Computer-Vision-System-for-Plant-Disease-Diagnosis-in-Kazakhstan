# MVP verification record

Date:21 October2026, Asia/Aqtau. This is an execution record, not an inferred checklist.

## Commands executed

| Layer | Command | Observed result |
|---|---|---|
| Python dependencies | uv sync; uv sync --frozen | Locked Python3.12 environment installed |
| PostgreSQL | docker compose up -d --wait db | PostgreSQL17.6 healthy, persistent local volume |
| Migrations | uv run alembic upgrade head; uv run alembic check | Applied; no new upgrade operations detected |
| Backend/runtime tests | uv run pytest -q --tb=short | 63 passed in final integrated run (8.34 s), including two Docker configuration regressions; one dependency deprecation warning |
| Meaningful failure tests | tests/integration/test_process_recovery.py | Actual SIGKILL after claim, before commit and after commit; all3 pass |
| Ownership/replay/input | tests/integration/test_security_and_contract.py | Cross-owner reads/links/download denied; concurrent replay one effect; image byte/pixel/geometry guards; immutable ready/terminal rows |
| Review regressions | tests/integration/test_review_regressions.py | Watched stale observation, transient upload retry and cleanup regressions fail then pass |
| Runtime | uv run pytest tests/runtime -q |33 tests pass after source/projected-allocation guard; exact tensors of3 real crop images match preguard preprocessing |
| Lint | uv run ruff check server tests scripts ml | Passed in integrated run |
| Client | uv run python scripts/export_openapi.py; pnpm generate:client; pnpm typecheck | Actual OpenAPI export, generated client and both TS projects passed |
| Mobile flow | pnpm test:mobile |14 tests passed again in integrated run; native QA recorded separately |
| Expo compatibility | expo install --check; expo-doctor | Dependencies aligned;20/20 doctor checks passed |
| Android JS | expo export --platform android --output-dir dist |828 modules,2.6MB Hermes bundle, export success |
| Native build | Android Gradle assembleRelease, signature verification | Final ARM64 APK27,401,576 bytes built44s; v2 signature/native ARM64 library verified. Updated x86_64 APK installed in API30 emulator |
| Native emulator flow | Installed x86_64 APK on Android30 AOSP | Login → gallery JPEG → preview → upload/poll → real research candidates → feedback → history → private photo reopen passed; screenshots reviewed; no AndroidRuntime/ReactNativeJS error log |
| Live full chain | scripts/e2e.py with admitted wheat/potato/tomato images | All3 passed queued→running→completed, real candidates, inconclusive; replay preserved result; actorB denied |
| Docker packaging | bounded buildx build --load; isolated Compose backend on port8001 | Image built with frozen dependencies, nonroot user, API/worker healthy; actual wheat queued→running→completed with3 real candidates, inconclusive; replay and cross-owner denial passed |

## Evidence and limits

- Measured ML results, source licenses/provenance, quarantines, proxy-group limits and parity: [DATA_AND_MODEL](DATA_AND_MODEL.md) and model_reports JSON.
- Live run reports are private/local at runs/e2e-wheat.json, e2e-potato.json, e2e-tomato.json. These use public research samples, not agronomic diagnoses or independent national validation.
- Provider-backed OIDC login/refresh/revocation, a physical Android camera, independent Kazakhstan/source-held-out evaluation are not claimed.
- Tests run on a separate disposable agrovision_test database; local demo/history remains in agrovision.
- One dependency deprecation warning remains in Starlette's test client/AnyIO compatibility alias; it does not fail verification. No accuracy/latency claim is made from unit test success.

## Final integration rerun

Integrated source checks completed:63 Python tests passed,14 mobile tests passed, both TypeScript projects passed and Ruff passed. Native emulator E2E passed and final signed ARM64 artifact built. Docker smoke passed as recorded below. Main branch pushed successfully; source/packaging commit4951c34 passed hosted CI. Final evidence-only documentation commit follows without changing executable source.

### Executed Docker smoke

Built `agrovision-local:0.1` from the digest-pinned Python3.12.13 base with `uv sync --frozen --no-dev`; image ID `sha256:d4ec50add5475720d983c311e98730956d0ff916df8ce2079ab648913e0650de`. Build context was193.57kB, excluding local models, photos, datasets and credentials. Dedicated BuildKit container limits were verified as2GiB memory,2GiB total memory+swap (no extra swap),2 CPU cores. The global default builder was unchanged.

The isolated override used localhost8001, a separate `agrovision_docker_smoke` database and the Docker photo volume, so the existing local worker could not claim container jobs. API ran as nonroot `agrovision` with768MiB cap; separate worker with1GiB cap. Both started successfully after migrations. Catalog exposed wheat/potato/tomato with3 classes each and refused maize assessment capability. `scripts/e2e.py` using an admitted wheat photo observed queued→running→completed,3 real research candidates, mandatory inconclusive outcome, exact replay and denial of another owner. Private evidence: `runs/docker-build.log`, `runs/docker-smoke-start.log`, `runs/e2e-docker-wheat.json`.

After verification, only the smoke API/worker and dedicated builder were stopped. The local API/worker remained active, PostgreSQL remained available, and unrelated containers were untouched. Host available RAM after cleanup was9.49GiB. This is local Docker execution evidence, not a hosted CI/deployment claim.

## Remote handoff

Repository main: https://github.com/maqsatto/An-Intelligent-Computer-Vision-System-for-Plant-Disease-Diagnosis-in-Kazakhstan . Hosted [Verify MVP run39624323613](https://github.com/maqsatto/An-Intelligent-Computer-Vision-System-for-Plant-Disease-Diagnosis-in-Kazakhstan/actions/runs/39624323613) completed successfully for4951c34834a5276fe3d597a0c27e88d7cbfec22d: Python lint/tests, locked dependency installation, generated-client drift, both TypeScript projects, mobile tests and Android JS export. This is hosted source verification, not a hosted native APK build.

Final ARM64 APK is local at artifacts/android/agrovision-demo-arm64.apk; SHA2564195ad54c0777035727ab1d161d61c847811da951a91a772f5d6d88e03a6c2a1. It embeds the current LAN API192.168.8.61:8000. Local API/worker and PostgreSQL remain running. Emulator, Gradle, smoke API/worker and bounded builder are stopped.

## Model cases evaluation

The subsequent integrated Python run passed **73 tests**, including 10 evaluation regressions that require no local images, weights or GPU. Actual CPU replay covered the existing joint held-out 153 photos and PV held-out 88 photos; the paired comparison uses only 88 identical test SHA256s. [Measured cases](../evaluation/MEASURED_CASES.md) records errors, per-class/confusion results, deterministic perturbations, synthetic controls and bounded resources. These are additional local results; the earlier CI run and its commit above remain historical evidence, not a claim of a new hosted run.

## Current documentation-consistency verification

On 21 October 2026 (Asia/Aqtau), `uv run pytest -q --tb=short` passed **90 tests in 8.39 s**, followed by `pnpm test:mobile` with **14 passing tests**. This includes protocol consistency and evaluation regressions; it does not execute the planned ResNet18 experiment. The existing Starlette/AnyIO deprecation warning remains. The requirements matrix now links each current acceptance claim to the implemented checks and separates deferred functionality. Earlier test counts above are historical execution snapshots.
