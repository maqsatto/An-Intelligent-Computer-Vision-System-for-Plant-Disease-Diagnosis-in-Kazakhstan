# AgroVision Online MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Independent mobile and ML work is delegated as explicitly authorized by the user.

**Goal:** Deliver a presentable Android MVP with an honest model capability boundary and a verified durable online assessment flow.
**Architecture:** Modular FastAPI monolith, separate PostgreSQL-backed worker, private filesystem adapter, standalone ML runtime and Expo mobile. OpenAPI generates the shared TypeScript client.
**Tech Stack:** Python 3.12, uv, FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Expo SDK 55 with its matching React Native, pnpm, ONNX CPU runtime.
**Spec:** ../specs/2026-10-21-online-vertical-design.md

## Global Constraints

- Main agent alone owns Pydantic schemas, DB migrations and API/worker state protocol.
- One primary photo per assessment; owner checks on all personal resources; UUID is not authorization.
- Atomic assessment/job, owner-scoped idempotency, immutable pinned model, bounded retries and lease fencing.
- No production synthetic diagnosis; no claimed Kazakhstan accuracy without evidence.
- No web UI. Offline capture queue follows the stable online MVP.
- No datasets, user photos, weights, credentials or fabricated YouTrack IDs in Git.

## Review Focus

- Concurrent idempotent submission must produce one assessment/job, including after model changes.
- Expired final attempt must fail rather than remain running forever.
- Photo upload and deletion must synchronize at finalization, without long DB IO transactions.
- No model/crop support may be inferred from illustrative catalog entries.
- Token/logout/account change must not leak another account's history or photo.

### Task 1: Repository and reproducible environment
**Files:** .gitignore, pyproject.toml, uv.lock, compose.yaml, .env.example, docs/development/PROGRESS.md.
**Interfaces:** database URL and environment configuration shared by API/worker; independent runtime module agrovision_runtime.
- [ ] Create Git branch and baseline docs commit; preserve Foundation unchanged.
- [ ] Fix Python dependencies and PostgreSQL local profile; verify clean import and DB connection.
- [ ] Commit environment without datasets/secrets.

### Task 2: Durable server vertical
**Files:** server/agrovision/**, server/migrations/**, tests/**.
**Interfaces:** /v1 DTOs from Foundation; runtime Predictor accepts normalized image bytes plus crop/organ and returns AssessmentResult-compatible dict; bundle snapshot persisted at submission.
- [ ] Write failing integration tests for creation/upload/idempotency/ownership/no model.
- [ ] Implement validated bearer auth, catalog, observations, private photos and assessments.
- [ ] Write failing recovery/fencing/retry tests on PostgreSQL; implement short claim/finalize and supervised inference outside transactions.
- [ ] Run migrations and integration tests; commit verified server.

### Task 3: Runtime, dataset admission and reproducible baseline
**Files:** ml/**, tests/runtime/**, docs/development/DATA_AND_MODEL.md.
**Interfaces:** agrovision_runtime BundleRegistry/validate_bundle/Predictor; no FastAPI/ORM imports; runtime manifest conforms shared docs/development/RUNTIME_INTERFACE.md.
- [ ] Audit Foundation sources and conditions using primary sources; download admissible pilot data outside Git with hashes/provenance.
- [ ] Write failing manifest/preprocessing/label-order tests; implement CPU ONNX adapter and fail-closed admission.
- [ ] Prepare bounded real baseline training/export/evaluation where resources/data permit; record actual commands/results, never invent validation.
- [ ] Verify fixed-fixture parity if actual export exists; document absent evidence otherwise.

### Task 4: Android application and generated client
**Files:** apps/mobile/**, packages/api-client/**, package.json, pnpm-workspace.yaml, pnpm-lock.yaml.
**Interfaces:** contract DTOs /v1 from Foundation plus explicit availability_reason and runtime_mode; generated schema at packages/api-client/src/schema.d.ts. Mobile requests use bearer auth, stable UUID keys and private photo Authorization.
- [ ] Read Figma contexts/screenshots for actual screens; implement RN native layout, camera/gallery, preview, send/poll/result/error/history.
- [ ] AuthSession OIDC and SecureStore with explicit local-development token mode only; conspicuous dev predictor banner.
- [ ] Generate client from live OpenAPI; typecheck and mobile contract/render tests.
- [ ] Verify Expo dependency compatibility and Android build/export where environment permits.

### Task 5: Integration, independent review and demonstration
**Files:** README.md, scripts/**, docs/development/VERIFICATION.md, CI workflow.
- [ ] Start real PostgreSQL/API/worker; run end-to-end fixture flow and cross-owner/concurrency/restart checks.
- [ ] Obtain independent review, fix material findings and rerun covering tests.
- [ ] Record exact commands, results, limitations, model provenance and next bounded increment.
- [ ] Commit final integrated MVP and show Git status/log. Do not publish/push without a configured authorized destination.
