# Backend independent review

Read-only implementation review, 21 October 2026. No tests rerun. Findings refer to the current early vertical; backend owner should add focused regression checks.

## P1 — Refresh the observation when reacquiring its lock

`server/agrovision/assessments/service.py:43–49`, with `server/agrovision/db.py:17`: the service retains an ORM observation across `commit()`, while the session uses `expire_on_commit=False`. A subsequent `SELECT ... FOR UPDATE` returns the same identity-map instance without repopulating attributes. If deletion commits during model validation, `owned(..., lock=True)` can see stale `deleted_at=None` and create a new assessment against an already deleted observation. Use an explicit refresh/populate_existing under the observation lock. Regression: pause select_model, delete in a separate session, resume create and require rejection with no new assessment/job.

## P1 — Upload retries cannot recover after a transient failure or process death

`server/agrovision/photos/service.py:62–65,88,98–101`: a pending reservation is committed before storage, and every non-ready replay returns 409 forever. Storage errors mark failed but failed rows follow the same permanent rejection. A process death after reservation has the same effect. The client is explicitly told to repeat later, but the same client_photo_id can never complete. Implement safe recovery/retry under a reservation ownership/lease protocol, including abandoned pending uploads. Regression: fail storage once, then replay identical bytes/key after recovery; also simulate an abandoned reservation.

## P1 — Deletion has no eventual private-blob cleanup

`server/agrovision/observations/service.py:143–165` only commits a tombstone and cancels work; `server/agrovision/app.py:158` reports deletion_pending. No cleanup worker or sweep exists in server/scripts; the only store.delete call compensates an unsuccessful upload finalization. Thus all successfully uploaded private images remain forever after deletion; partial writes and abandoned reservations also accumulate. Add an idempotent bounded cleanup routine driven by tombstones/reservation age, with grace time and IO outside DB locks. Keep download denial immediate as currently implemented.

## P1 — The ONNX session is reopened after checksum validation

`ml/runtime/agrovision_runtime/__init__.py:64,129,193–198`: bundle validation hashes a file, then opens it by path; predictor construction validates again and opens yet another session by path. Replacing the active ONNX file between validation and the final session open can execute different weights while the committed assessment still reports the pinned original artifact digest. Metadata/manifest equality after construction does not detect a same-contract weight replacement. Load the exact hashed immutable bytes into ORT, or publish immutable content-addressed bundles and bind validation/session to one immutable artifact. Regression: replace the artifact on the final session-opening boundary and ensure execution rejects or still uses the validated bytes.

## P2 — Warm cache rejects a legitimate second manifest sharing weights and policy version

`server/agrovision/assessments/predictor.py:56–74`: cache key contains artifact hash, model mode and policy version only, but equality later compares the entire manifest. A second valid release using unchanged weights/policy version with updated provenance, release version or preprocessing produces the same cache key and is permanently failed bundle_mismatch until worker restart. Key cache by canonical full manifest digest (or all immutable release pins), retaining equality checks. Regression: process two independently valid manifests with identical weights and different version/provenance in one persistent predictor.

## P2 — Catalog and assessment eligibility disagree for maize

`server/agrovision/catalog/service.py:29,49–51`: select_model unconditionally rejects crops outside PILOT_CROPS, whereas catalog sets can_assess from bundle.supports without the same eligibility filter. A valid bundle supporting maize causes UI to advertise an available analysis that always fails 422. Apply the configured eligibility scope consistently to catalog and selection.

## Inspected behaviors without additional findings

Production rejects explicit development credentials, synthetic predictor and research bundles; authentication validates RS256 signature, issuer, audience, expiry and nonempty subject. Development intentionally accepts only its separate HS256 issuer (it does not exercise OIDC login/refresh). Observation/photo composite foreign keys prevent cross-owner and cross-observation inputs. Assessment idempotency insertion is committed with its job; unique conflict recovery rolls back before replay. Queue mutation order is observation → assessment → job; finalize checks current token, running state and DB-clock lease. Expired last-attempt jobs become terminal. Existing cached predictors compare full pinned manifest before inference. Context-photo selection is allowed by the Foundation contract, which says purpose is a UI aid, so it is not reported as a bug.

# Follow-up review of fixes

Source reviewed after recoverable upload, cleanup, cache, catalog and exact-byte ORT amendments. No tests rerun. Original stale ORM, permanent upload retry, missing cleanup, artifact reopen, cache identity and maize scope findings are addressed in source. Regression tests exist for the stale ORM, transient retry and ordinary deletion cleanup paths; test execution remains with the backend owner. Exact-byte ORT admission and manifest snapshots remove the reported path reopen race.

Upload locking remains observation → photo throughout reservation, failure handling and finalization. No new deadlock cycle found: each upload locks one observation, and same-client cross-observation contenders do not acquire the winner's observation after acquiring its photo. Different uploads can wait on the common client uniqueness constraint but the transaction owning it does not need their observation lock.

## Remaining P2 — Cleanup scan permanently starves newer orphans

`server/agrovision/photos/cleanup.py:62–72`: the scanner sorts every file and slices to the oldest limit before checking references. Once 100 older healthy ready-image files exist, every cleanup run repeatedly examines those same referenced files; newer abandoned object files never enter the candidate set. Also, sorting all files is unbounded work despite the routine's bounded claim. Use a persistent advancing scan cursor/batch iterator (or explicitly queue replaced reservation keys) so each file eventually receives inspection. Regression: limit live older files plus one newer orphan, run enough batches and require orphan deletion while preserving live images.

## Remaining P2 — Late write after deletion cleanup can retain a referenced deleted blob forever

`server/agrovision/photos/cleanup.py:44–59,71–72`: an upload can have a committed reservation but not yet have created its file. Delete its observation, then run cleanup: it marks pending failed, sees no file and records blob_deleted_at. If the uploader subsequently writes and dies before compensating during finalization, the blob exists with a still-referenced key and blob_deleted_at set. The DB sweep excludes it forever, while the filesystem sweep excludes any referenced key irrespective of tombstone/deletion marker. Let the filesystem sweep reclaim tombstoned/marked-deleted references after grace, or persist explicit deletion work which remains valid for late arrivals. Regression: reserve → tombstone/cleanup before store.put → write → simulate process death → later cleanup must remove the blob.

## Remaining P2 — A filesystem cleanup race terminates the assessment worker

`server/agrovision/photos/cleanup.py:63–69`, `server/agrovision/assessments/worker.py:29`: files can vanish between is_file/stat calls and between building paths and checking their mtime, due to another worker's cleanup or upload compensation. FileNotFoundError from either stat is outside the OSError handlers. cleanup_once runs before run_once's exception boundary; this exits the worker process and stops queued assessment processing until supervisor restart. Handle expected per-entry disappearance, and isolate/log cleanup failures from job processing. Regression: delete an entry between enumeration and stat (or run simultaneous cleanup batches) and require clean completion and continuing queue processing.

# Final scoped cleanup rereview

Read the amended streaming scanner, filesystem reference eligibility and the two added cleanup regressions; no tests executed by this reviewer.

All three follow-up findings are addressed for the reported scenarios: the scanner advances between bounded batches instead of repeatedly slicing old live files; the filesystem pass reclaims stale tombstoned/failed/expired references even when a previous sweep set blob_deleted_at; expected entry disappearance during is_file/stat/unlink is contained. The two new tests model orphan starvation and late resurrection after deletion cleanup. No additional material issue found in those fixes.

The filesystem pass's nonlocking eligibility read does not introduce a ready-photo deletion race in the current upload protocol: retry always assigns a new random object key, and finalization cannot publish an expired reservation. Healthy ready keys remain protected. Mutation locks remain observation → photo. Worker still runs cleanup before its job-processing exception boundary; this does not invalidate the disappearance fix, though general directory/DB outages can still require process restart and should be handled by its deployment supervisor.
