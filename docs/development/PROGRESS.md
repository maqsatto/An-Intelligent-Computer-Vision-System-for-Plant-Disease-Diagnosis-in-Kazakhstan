# AgroVision implementation ledger

User authorized full MVP development and Git on 2026-10-21. Foundation spec approved for implementation by that request.

- Initial state: new repo initialized on feat/online-mvp. No preexisting product code or Git history.
- Execution: main owns backend/contract/migrations; independent mobile and ML agents allowed by original user request.
- Ruling: proceed directly from user instruction to development without another plan approval gate; the user explicitly said to start development completely.
- Real YouTrack IDs unavailable; commit messages describe actual changes without invented IDs.

- Task1 complete: Git/locks and bounded PostgreSQL environment installed; origin linked and verified empty before changes.
- Task2 complete: durable API/worker, immutable pins/results, ownership/idempotency, recoverable uploads and cleanup; initial review findings fixed with red→green evidence.
- Task3 complete: actual D01/D05 data,9-class real research bundle, measured report/parity and production rejection; source owner commit73d25da.
- Task4 complete: native mobile/types/tests/export, actual emulator end-to-end flow and final signed ARM64 APK; physical phone remains an explicit follow-up.
- Task5 local verification complete: all3 live crop flows/replay/ownership, independent review and input guards, isolated bounded Docker build/full-flow smoke. Main pushed normally; hosted CI run39624323613 passed. Evidence and remaining physical-device/OIDC limitations are recorded in VERIFICATION.md.
- Ruling: research runtime was added after user explicitly requested dataset-backed MVP; it always abstains and does not waive diagnostic release gates. Cost if wrong: users need clearer research wording; no production diagnostic release is activated.
- Ruling: use actual Node26.12 native toolchain after successful compatibility/build checks rather than proposed uninstalledNode22; exact version recorded. Cost if wrong: reproduce on recommended LTS and rerun native compatibility.
- Ruling: replace Android MemoryHigh2500MiB/Max3GiB with Max4GiB/Highinfinity/Swap0 plus admission/lowweights; old threshold caused observed reclaim thrash despite available RAM. Cost if wrong: reduce native concurrency or wait, never crowd desktop.
