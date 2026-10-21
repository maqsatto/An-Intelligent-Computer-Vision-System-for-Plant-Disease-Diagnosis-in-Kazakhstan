#!/usr/bin/env bash
set -euo pipefail
mobile_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$mobile_dir/../.." && pwd)"
toolchain_dir="${AGROVISION_TOOLCHAIN_DIR:-$HOME/.cache/agrovision}"
# Bound the entire process tree, including Kotlin/Node/native compiler children.
if [[ "${1:-}" != "--inside-budget" ]]; then
  available_kib="$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
  if (( available_kib < 6291456 )); then
    printf 'Waiting for at least 6 GiB available RAM; no heavy process started.\n' >&2
    exit 75
  fi
  exec flock -n -E 75 "$toolchain_dir/heavy.lock" systemd-run --user --scope --unit="agrovision-android-build-$$" \
    -p MemoryHigh=infinity -p MemoryMax=4G -p MemorySwapMax=0 \
    -p CPUQuota=200% -p CPUWeight=10 -p IOWeight=10 -p TasksMax=128 \
    "$mobile_dir/scripts/build-demo-android.sh" --inside-budget
fi
android_archs="${AGROVISION_ANDROID_ARCHS:-arm64-v8a}"
apk_filename="${AGROVISION_APK_FILENAME:-agrovision-demo-arm64.apk}"
: "${EXPO_PUBLIC_API_URL:?Set the API origin reachable from your phone, e.g. http://192.168.1.10:8000}"
export EXPO_PUBLIC_AUTH_MODE=development
export NODE_ENV=production
export JAVA_HOME="$toolchain_dir/jdk"
export ANDROID_HOME="$toolchain_dir/android-sdk"
export GRADLE_USER_HOME="$toolchain_dir/gradle"
export PATH="$JAVA_HOME/bin:$PATH"
cd "$mobile_dir"
pnpm exec expo prebuild --platform android --no-install
cd android
native_budget_args=()
if [[ "${AGROVISION_SERIAL_NATIVE:-0}" == "1" ]]; then
  native_budget_args=(--init-script "$mobile_dir/scripts/serial-native.gradle")
fi
./gradlew assembleRelease --no-daemon --max-workers=1 "${native_budget_args[@]}" \
  -Dorg.gradle.parallel=false \
  -Dorg.gradle.jvmargs='-Xmx1536m -XX:MaxMetaspaceSize=384m -XX:ActiveProcessorCount=2' \
  -Pkotlin.compiler.execution.strategy=in-process \
  -PreactNativeArchitectures="$android_archs"
mkdir -p "$repo_dir/artifacts/android"
cp app/build/outputs/apk/release/app-release.apk "$repo_dir/artifacts/android/$apk_filename"
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose "$repo_dir/artifacts/android/$apk_filename"
sha256sum "$repo_dir/artifacts/android/$apk_filename"
