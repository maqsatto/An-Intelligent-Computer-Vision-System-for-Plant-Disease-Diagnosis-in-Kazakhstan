# Android MVP implementation and verification

Implemented 2026-10-21 in `apps/mobile`, Expo SDK 55.0.31 / React Native 0.83.10 / React 19.2.0. Native Android app; no web UI. The monorepo dependency graph is pinned in `pnpm-lock.yaml`; pnpm 11.25.0.

## Scope

- Real server catalog drives crop selection and availability; unsupported known crops save observation + photo without inference.
- Camera and Android system gallery selection, permission handling, one primary JPEG, orientation normalization and 2048 px longest edge, preview and optional bounded notes.
- Observation/upload/assessment are separate steps with stable UUIDs and idempotency key preserved for online retry. Polling stops at terminal state, navigation, background, logout or cancellation and uses interval backoff.
- All completed outcomes, pending and processing failure have distinct copy. No fabricated predictions, history, accuracy percentages or inference offline. Research inference, synthetic runtime and development auth have explicit banners.
- Real owner history with cursor pagination, private image content with bearer header, same-origin URL enforcement, feedback and deletion.
- OIDC discovery + Authorization Code PKCE, external login browser, refresh token in native SecureStore only, memory-only access token. Local explicit development mode accepts operator-issued bearer in memory. On 401 the app requires login, without a retry loop. Logout clears personal state and aborts requests; late history results are fenced by session epoch.
- Figma high-fidelity context and screenshot read for nodes `4:49`, `4:50`, `4:52`, `4:54`. Tokens, 56 px actions, card dimensions/gaps, headings and Android Material navigation adapted to native responsive components. The prototype illustration and fabricated rows were replaced by real user photo / real owner records as required by the Foundation. OS status bar is real, not drawn.

## Verified commands

- `pnpm install` — success; dependency lock created.
- `pnpm --filter @agrovision/mobile exec expo install --check` — dependencies up to date.
- `cd apps/mobile && pnpm dlx expo-doctor` — **20/20 passed**.
- `pnpm test:mobile` — **14/14 passed** (stable retry IDs and upload recovery; no inference for unavailable crop; terminal/abort polling; all outcomes and unknown code fallback; image-origin/bearer protection; 401 no blind retry; idempotency header; fetch cancellation; bounded long-running poll pause).
- `pnpm --filter @agrovision/mobile exec expo export --platform android --output-dir dist` — success, **828 modules**, Android Hermes bundle **2.6 MB**. This verifies bundling, not APK installation/device behavior.
- `pnpm exec openapi-typescript packages/api-client/openapi.json -o packages/api-client/src/schema.d.ts` — generated from actual FastAPI OpenAPI, not handwritten DTOs.
- `pnpm typecheck` — both API-client and native mobile **passed** against generated schema.
- Final Android export and all **14/14** tests rerun after session/poll/retry fixes — passed.

## Run

1. Start API/worker according to root README.
2. Copy `apps/mobile/.env.example` to `.env` and set API origin reachable from Android. `10.0.2.2` is Android emulator host; a real device needs computer LAN IP.
3. For local demo choose development auth and use backend-generated signed operator token. For production configure OIDC issuer/client and `agrovision://` redirect allowlist, HTTPS API, native development/release build.
4. `pnpm mobile`, then open in the matching Expo Go SDK 55 or native Android build. `pnpm --filter @agrovision/mobile android` requires Android SDK/JDK.

## Practical limits

The initial environment had no JDK/Android SDK. A local isolated toolchain was subsequently installed under `~/.cache/agrovision`; native APK build status is recorded below. Native emulator visual and integration QA is recorded below. No physical camera test, OIDC provider login or physical-device accessibility QA is claimed. Android export and generated-schema typecheck are distinct checks. Camera needs a physical device; Expo Go custom OIDC redirects require a development build. Offline persistent queue, multilingual agronomic copy, field selection and crash telemetry are intentionally outside this online MVP. Local draft is in memory: closing the process before server save loses the unsent draft. Photos/results are never invented to hide unavailable server/model state.


## Native APK build work

Official local-only toolchain: Temurin JDK 17.0.20.1+1, Google Android CLI 13114758, Android platform 36 / build tools 36.0.0, generated Expo Gradle 9.0.0 wrapper. JDK archive SHA256 verified against Adoptium metadata: `3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e`. Android CLI archive SHA256 recorded: `7ec965280a073311c339e571cd5de778b9975026cfcbe79f2b1cdcb1e15317ee`.

Sources: [Temurin release](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20.1%2B1), [Google CLI archive](https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip).

`apps/mobile/scripts/build-demo-android.sh` reproduces the local demo build using an explicitly supplied phone-reachable API origin and development auth. Generated native Android project and debug signing key are ignored. The first successful build used one Gradle worker and Xmx2048m. After system memory pressure, the script was tightened to an entire-process-tree systemd user scope: MemoryMax=3G, MemoryHigh=2500M, MemorySwapMax=512M, CPUQuota=200%, TasksMax=128; Gradle Xmx1536m / metaspace384m / ActiveProcessorCount2, in-process Kotlin and one Metro worker. That low MemoryHigh proved too restrictive for Ninja and caused reclaim/I/O self-thrashing. The final guard was corrected to MemoryMax=4G / MemoryHigh=infinity / MemorySwapMax=0 / CPUWeight10 / IOWeight10 with >=6GiB available admission. Only one heavy ML/build/emulator workload may run at a time. The local plugin permits cleartext HTTP only for explicit development prebuilds. Intended output is an ARM64 standalone APK, release variant with debug signing, for local demonstration only.

The demo embeds `http://192.168.8.61:8000`; API and worker must run on that reachable LAN origin. Rebuild if the server address changes. Release variant uses a generated ignored debug signing key, suitable for local demonstration, not store distribution.

## Native Android evidence

On 2026-10-21, the matching x86_64 APK was installed and run on an Android 30 AOSP emulator (390 × 844, density 160). Android 36 Google APIs was too memory intensive for the workstation guard; the lighter disposable API30 AVD completed the flow. This is native Android emulator QA, not physical-phone validation.

Observed native flow: operator bearer login → server crop catalog → tomato → Android system gallery → admitted D01 tomato test-split JPEG → normalized image preview → observation/photo upload → asynchronous polling → actual joint research model result → saved useful-result feedback → actual owner history → reopened result with private authenticated photo. Model displayed `pilot-joint-efficientnet-b0-seed17` with three research hypotheses (early blight, late blight, healthy appearance), explicitly withheld diagnosis. No fake prediction or history rows were used. The original test JPEG SHA256 is `b69f11481999b86f47ff46ced455727440f38d40c5fcc7ec71bece917f58a9e1`. The private token was read from a temporary file, never printed or stored in repository artifacts.

Screenshots were visually inspected:

- `artifacts/android/qa/01-home.png` — native home.
- `artifacts/android/qa/07-preview.png` — real selected photo and upload preview.
- `artifacts/android/qa/10-hypotheses.png` — actual research hypotheses and model version.
- `artifacts/android/qa/12-history.png` — server owner history.
- `artifacts/android/qa/13-reopened-result.png` — reopened result with authenticated private photo.

`adb logcat -d -s AndroidRuntime:E ReactNativeJS:E` contained no errors after the full flow. The system picker was operated with Android keyboard navigation when touch navigation did not enter its folders; the selected file was returned by the real system picker. Camera capture, actual OIDC provider, offline use and phone hardware remain unverified.

Matching native QA APK: `artifacts/android/agrovision-demo-x86_64.apk` (27 MiB), SHA256 `51255bf95cf6ba17097c253f09ca5641a2755efee72d957a32cca5ef259483a9`; v2 signature verified. ARM64-only APK cannot be tested through this emulator's RN SoLoader/native-translation ABI selection, so a matching x86_64 build was used.

During native-source review, RN 0.83's `abort-controller@3` was found to lack `AbortSignal.throwIfAborted` and `reason`; the flow uses portable abort checks and a standard named AbortError. Native-compatible signal/delay regression tests pass. Final `pnpm typecheck` and `pnpm test:mobile` were rerun after native QA: both typechecks and **14/14 tests passed**.

## Final phone artifact

Final current-source phone APK: `artifacts/android/agrovision-demo-arm64.apk` (27 MiB), SHA256 `4195ad54c0777035727ab1d161d61c847811da951a91a772f5d6d88e03a6c2a1`. Guarded warm build **succeeded in 44 seconds**, 340 tasks (21 executed, 319 up-to-date). Android APK v2 signature and embedded `lib/arm64-v8a/libreactnative.so` verified. This contains the current research-model copy and native-compatible cancellation fixes. Build log: `~/.cache/agrovision/android-build-arm64-final.log`.

The ARM64 artifact is installable locally with `adb install -r artifacts/android/agrovision-demo-arm64.apk` on a matching ARM64 Android phone; a physical phone was not available for validation. A successful native x86_64 flow verifies the same JS source and backend integration. All owned emulator, Gradle and helper processes exited after verification; the heavy slot was released.
