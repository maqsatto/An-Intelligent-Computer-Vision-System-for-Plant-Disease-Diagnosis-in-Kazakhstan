# AgroVision Android

Native Expo SDK 55 app. From the repository root:

```sh
pnpm install --frozen-lockfile
cp apps/mobile/.env.example apps/mobile/.env
pnpm mobile
```

Set `EXPO_PUBLIC_API_URL` to the API **origin**, without `/v1`. On Android emulator use `http://10.0.2.2:8000`; on a real phone use the computer's reachable LAN IP. Phone and computer must share network access. The API and worker must be running separately.

For local demo explicitly set `EXPO_PUBLIC_AUTH_MODE=development`, then paste a backend-generated signed operator token into the app's login screen. The app never treats an actor UUID as authentication and never persists that development token. The synthetic predictor is visibly marked and cannot produce a diagnostic claim.

For deployed use set `EXPO_PUBLIC_AUTH_MODE=oidc`, issuer and client ID. Register the AuthSession redirect `agrovision://` URI with the OIDC provider; exact generated redirect can vary by native build, so check provider configuration. Use a development/native build for OIDC custom scheme redirects and HTTPS for the API. Only refresh tokens are persisted, in native SecureStore; access tokens remain in memory.

Checks:

```sh
pnpm typecheck
pnpm test:mobile
cd apps/mobile
pnpm dlx expo-doctor
pnpm exec expo export --platform android --output-dir dist
```

`pnpm --filter @agrovision/mobile android` requires local JDK and Android SDK. Android bundle export is not an APK and does not prove camera/device behavior. Use the SDK 55 compatible Expo Go to preview camera/gallery and local token flow on a phone, or build a native app.

There is no persistent offline queue in this online MVP. An unsent photo/draft is kept in memory, and closing the process loses it. Successful server saves and accepted assessments remain visible in history. Leaving the analysis page stops local polling; an accepted server job continues. Return via history to resume.

## Standalone local demonstration APK

The local build script expects Temurin JDK 17 in `~/.cache/agrovision/jdk` and Google Android SDK in `~/.cache/agrovision/android-sdk` (platform 36, build tools 36.0.0; Gradle downloads the required native toolchain). All tools/builds stay outside Git. Override `AGROVISION_TOOLCHAIN_DIR` if installed elsewhere.

```sh
EXPO_PUBLIC_API_URL=http://YOUR_COMPUTER_LAN_IP:8000 apps/mobile/scripts/build-demo-android.sh
```

This produces `artifacts/android/agrovision-demo-arm64.apk`, a standalone ARM64 Android app with embedded JS, **development auth**, and HTTP LAN access enabled only in that explicit development configuration. Its release build variant uses the generated **debug signing key** and is suitable for local demonstration only. It is not a production/store release. The API URL is compiled into the bundle; rebuild for another server. Never paste a bearer token into a build variable or Git.

For production prebuild without `EXPO_PUBLIC_AUTH_MODE=development`; the local config plugin disables cleartext HTTP. Production still requires actual OIDC configuration, HTTPS, release signing management and device QA.


Build resource guard: the script runs the entire Gradle/Kotlin/Node/compiler tree inside a systemd user scope with a 4 GiB memory cap, no scope swap, no low MemoryHigh threshold, low CPU/I/O weights and 200% CPU quota. It starts only with at least 6 GiB host RAM available. Gradle uses one worker, Xmx1536m and in-process Kotlin. Run only one heavy build, model-training job or emulator at a time on this workstation. The scope mechanism was smoke-checked after the memory incident; the final native refresh runs only in its assigned heavy slot.

For the native x86_64 emulator QA artifact, use `AGROVISION_ANDROID_ARCHS=x86_64 AGROVISION_APK_FILENAME=agrovision-demo-x86_64.apk` with the same script after the heavy slot is available. The ARM64 phone artifact should be kept separately. React Native SoLoader did not support running the ARM64-only package through this emulator's native-translation ABI selection.

`apps/mobile/scripts/run-qa-emulator.sh` uses the same memory/CPU and admission guard and shared `flock` as the native build, preventing those two scripts from overlapping. Exit75 means another guarded build/emulator holds the heavy lock. Model training must still be scheduled separately by the operator. Do not start the emulator until the native build process tree has exited.

For a cold build, optional `AGROVISION_SERIAL_NATIVE=1` configures CMake compile/link job pools of depth1; `--max-workers=1` alone does not limit Ninja. Adding these CMake arguments changes the native build cache key, so warm final builds keep their existing arguments. The optional pool path has not yet been exercised in the final build.
