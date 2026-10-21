# Independent final implementation review

21 October 2026. Read-only review of the current working tree, including untracked mobile/packaging files. No tests, apps, builds, account access or heavy reproductions were run. Existing test results belong to their executing agents. Native device/emulator QA remains a separate acceptance condition.

## P1 — Bound intermediate resize dimensions before allocating (addressed)

**Location:** `ml/runtime/agrovision_runtime/__init__.py:195–196`; accepted-input boundary: `server/agrovision/photos/service.py:25–26`.

**Trigger:** An authenticated actor uploads a valid, highly elongated JPEG/PNG and requests a research or validated assessment. A 10×60,000 JPEG has only 600,000 source pixels, so it passes the 20 MP upload check. Resizing its shorter side to 256 creates a 256×1,536,000 intermediate image (393,216,000 pixels) before the 224 crop. Pillow RGB image storage alone can exceed the worker container’s 1 GiB cap. The timeout does not bound peak memory allocation. Still more elongated inputs amplify the allocation further.

**Effect:** A small valid upload can kill/restart the predictor or worker under its memory cap, consume all three attempts and deny processing capacity to other queued observations. The unbounded allocation also exists when the public runtime is used outside the capped Docker profile. This is established by source control flow and dimension arithmetic; no dangerous allocation was executed.

**Smallest correct remedy:** Compute the intermediate dimensions first and reject inputs exceeding an explicit safe pixel/dimension budget before calling resize. Apply the same admission rule at upload (a clear input error) and runtime (defense for direct callers), or implement a bounded mathematically equivalent resize/crop and verify parity. Preserve the current preprocessing/version binding; do not silently change model tensors. Add a tiny elongated-image regression that verifies rejection before resize and ordinary-image parity; no large allocation is needed.

## Other reviewed boundaries

No additional material finding in the inspected ownership, owner-scoped idempotency, atomic assessment/job commit, global lock order, lease token/deadline fencing, final-attempt recovery, immutable result/photo guards, signed owner-authenticated downloads or amended cleanup paths. Prior backend-review fixes are reflected in source.

Research admission remains explicit and development/test only; research prediction always abstains, keeps global scores and returns null prediction. Production rejects research/synthetic configuration. The trained-data report accurately identifies dedup-proxy wheat groups, source confounding, uncalibrated scores and lack of independent Kazakhstan/OOD evaluation. Training selects the checkpoint on validation, reports held-out results after selection and makes no calibration-fit claim. These are research limitations, not new implementation requirements.

Generated-client transport and mobile submission use the documented UUID/key protocol and bearer image headers. Mobile source cancels active polling on navigation/background, keeps retry identifiers and separates research candidates from diagnostic conclusions. Provider-specific OIDC and native camera/gallery behavior still require the separately documented integration QA; source review cannot establish those outcomes.

Docker/Compose source includes migrations, shared private photo volume, explicit resource limits and development/production configuration gates. CI commands cover locked installation, Python checks, schema drift, TypeScript/mobile checks and Android JS export. No container build, hosted CI, native installation or benchmark was inferred from those command definitions.

## Scoped fix rereview

Read the amended runtime geometry validator/preprocess, upload admission, predictor error mapping, training call sites and focused regressions. No tests or heavy QA rerun by this reviewer. Main reports 56 passing tests (28 runtime, 28 integration); this is attributed execution evidence, not an independently executed result.

The reported P1 is addressed: source geometry is checked before decode/copy, projected resize geometry is limited to 4,000,000 pixels and 16,384 pixels per dimension before allocation, and upload rejects the same elongated input with 413. Runtime rejects it with InputImageError, mapped to nonretryable invalid_input rather than bundle_mismatch. EXIF swaps preserve the geometry predicates; runtime rechecks the transformed dimensions. Ordinary accepted-image resize/crop/normalization operations retain the existing pixel math, with exact-array compatibility regressions. Offline training explicitly permits up to 50 MP source images while retaining the same fixed intermediate cap; serving remains 20 MP. Historical measurements are not rewritten as fresh runs.

The regressions prohibit load, EXIF copying and resize on rejected runtime input, cover the source/projected/dimension boundaries, and exercise HTTP rejection. No new material finding in the affected code or call sites.

**Verdict:** No unresolved material finding in this scoped implementation review. Native/device QA, scientific diagnostic-release evaluation and provider-specific production integration remain separate documented acceptance conditions.
