# Implementation decisions and scope

Date: 21 October 2026. This supplements the preserved Foundation; it does not turn its proposed experiments into completed evidence.

## Actual code and environment

Python3.12.13/uv and Expo55/RN0.83/React19.2/pnpm dependencies are locked. Node26.12.0 is the verified native build toolchain.

`server/agrovision` groups observation, photo, assessment, catalog and identity behavior by function. Shared relational models/schemas keep foreign keys and one DTO vocabulary consistent. API/worker share a codebase and DB but run as separate bounded processes. The only external ports are the private ImageStore and Predictor. Training is a separate uv project; runtime has no training/FastAPI/ORM imports. There is no web UI, Kafka, Kubernetes, generic repository framework or separate ML service.

## Contract refinements

- `GET /v1/catalog` concretely defines `runtime_mode`, `availability_reason` and per-crop capabilities. Catalog IDs do not imply learned or validated support.
- Known pilot culture with no admitted model:503 model_unavailable; excluded culture such as maize:422 unsupported_crop. Unknown metadata IDs are invalid_crop/invalid_organ. All refuse before assessment/job creation.
- `AssessmentRead` is a generated discriminated union for queued/running, completed and failed. Completed outcome is independent of processing status. Request DTOs forbid unknown fields; timestamps require timezone offsets.
- `field_season_id` must be null until field ownership/CRUD exists. Feedback is implemented as a separate immutable-user-opinion record; it does not mutate results or supply reference labels.
- Photos are stored as normalized immutable JPEG. Public sha256 refers to those exact stored bytes; the separate original-input hash controls upload replay. Client UUID collision with different content/links/purpose is409.
- Private content URLs are relative, short-lived and additionally require bearer ownership. This is an explicit stronger local adapter rule; URLs alone do not authorize another actor.
- Two concurrent upload slots limit memory; saturation returns429 with Retry-After3. API/runtime also reject geometry that would expand beyond4MP/16384 pixels during shorter-side resize, even when compressed/source size is small.

## Durable state and image lifecycle

Unique owner+client IDs and owner+operation+idempotency key constraints enforce the single effect. The replay lookup precedes current model selection. Assessment, immutable full model manifest/snapshot and job commit together. Terminal results and pinned inputs are protected by database triggers; a completed result cannot be overwritten by retries or feedback.

Every queue mutation locks observation→assessment→job. Candidate IDs are read without locks, then eligibility is rechecked under SKIP LOCKED locks. DB clock governs leases; expired final attempts explicitly fail. Inference runs in a supervised subprocess with a hard budget and reuses a warm ONNX session. Actual SIGKILL tests cover after claim, before transaction commit and after commit; old lease completion/error writes are fenced.

Upload reserves a leased token/key in PostgreSQL, does decoder/storage IO outside DB locks, then locks observation→photo and rechecks tombstone/token/deadline before ready. Failed/expired reservations recover with the same client ID and a new immutable object key. Ready rows cannot be repurposed. Deletion immediately hides objects and fences work. Bounded cleanup removes tombstoned/failed/abandoned objects; its streaming directory cursor revisits late orphan writes without buffering a directory or starving behind old live files.

## Identity and release modes

Production validates configured OIDC RS256 tokens with issuer/audience/expiry checks; owner IDs derive from verified issuer+subject. Development can explicitly use separately signed short-lived operator tokens or configured OIDC. There is no arbitrary user-ID header. Mobile implements PKCE, SecureStore refresh credentials and provider revocation/logout; actual provider login/rotation is still an unexecuted integration check.

Three modes are kept distinct:

1. Production: only integrity/policy-validated releases; no actual diagnostic bundle is currently admitted.
2. Explicit research development: real trained multi-crop ONNX candidates, global scores, always inconclusive with research_model_unvalidated; no percentages presented as diagnosis.
3. Explicit synthetic development/test: infrastructure verification only, always inconclusive with no invented candidate.

The [measured report](DATA_AND_MODEL.md) documents sources, splits, parity and limitations. The historical training code snapshot is tied to source committed in73d25da; later input guards are recorded separately without rewriting measured provenance.

## Resource limits and operations

API memory cap768MiB; worker process tree1GiB; local DB512MiB. Heavy training and Android build/emulator tasks are serialized. Training completed under3GiB; Android native compiler children require a4GiB hard cap with no cgroup MemoryHigh reclaim threshold, no new swap, low CPU/I/O weights and ≥6GiB available-host admission. The earlier2.5GiB reclaim threshold caused avoidable I/O thrashing and was replaced; interactive resources recovered. Only this project's processes are controlled.

Local systemd scripts and the opt-in Docker backend profile are alternative runners, never run both on the same port. Model/dataset/image/token/signing-key files remain outside Git. Docker/profile readiness, APK installation and hosted CI must be reported only after their corresponding actual checks.

## Remaining bounded work

Persistent offline files/SQLite queue; reviewed diagnostic policy and independent external/local assessment; source-aware annotation workflow; localization; web client. Android emulator QA does not replace a physical phone camera/accessibility test. The project does not claim field readiness in Kazakhstan.

Official compatibility references rechecked: [ExpoSDK55](https://docs.expo.dev/versions/v55.0.0/) and [pnpm Node compatibility](https://pnpm.io/installation#compatibility). Node26 is supported by pnpm11; CI installs the pinned Node before pnpm rather than relying on the runner's older default Node. No latest package migration was performed.
