#!/usr/bin/env bash
set -euo pipefail
toolchain_dir="${AGROVISION_TOOLCHAIN_DIR:-$HOME/.cache/agrovision}"
export ANDROID_HOME="$toolchain_dir/android-sdk"
export ANDROID_AVD_HOME="$toolchain_dir/avd"
export ANDROID_USER_HOME="$toolchain_dir/android-user"
mkdir -p "$ANDROID_USER_HOME"
wipe_args=()
if [[ "${AGROVISION_EMULATOR_WIPE:-0}" == "1" ]]; then
  wipe_args=(-wipe-data)
fi
# The same lock prevents this script overlapping a native build.
  available_kib="$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
  if (( available_kib < 6291456 )); then
    printf 'Waiting for at least 6 GiB available RAM; no heavy process started.\n' >&2
    exit 75
  fi
exec flock -n -E 75 "$toolchain_dir/heavy.lock" systemd-run --user --scope \
  --unit=agrovision-android-emulator \
  -p MemoryHigh=infinity -p MemoryMax=4G -p MemorySwapMax=0 \
  -p CPUQuota=200% -p CPUWeight=10 -p IOWeight=10 -p TasksMax=512 \
  "$ANDROID_HOME/emulator/emulator" -avd "${AGROVISION_AVD_NAME:-agrovision-qa30}" \
  -no-window -no-audio -no-boot-anim -gpu swiftshader \
  -memory 1536 -cores 2 -skin 390x844 -dpi-device 160 -feature -Vulkan -no-snapshot "${wipe_args[@]}"
