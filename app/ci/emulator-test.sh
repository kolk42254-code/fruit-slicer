#!/usr/bin/env bash
# Runs inside the Android emulator job. Tests the debug APK over the WebView DevTools connection,
# then the real camera-permission dialog, then checks that the signed release APK installs and starts.
set -u
PKG=io.github.kolk42254code.fruitslicer
OUT=ci-out
mkdir -p "$OUT"
: > "$OUT/results.txt"
RC=0

note() { echo "$1" | tee -a "$OUT/results.txt"; }
running() { adb shell ps -A -o NAME 2>/dev/null | tr -d '\r' | grep -qx "$PKG"; }
devtools() {
  local s=""
  for i in $(seq 1 30); do
    s=$(adb shell cat /proc/net/unix 2>/dev/null | grep -o 'webview_devtools_remote_[0-9]*' | tail -1 | tr -d '\r')
    [ -n "$s" ] && break
    sleep 2
  done
  echo "devtools socket: $s"
  adb forward --remove-all
  adb forward tcp:9222 "localabstract:$s"
}

adb wait-for-device
# let the freshly booted emulator settle; hide crash/"not responding" dialogs of other apps where Android allows it
adb shell settings put global anr_show_background 0
adb shell settings put global hide_error_dialogs 1
sleep 20
note "android: $(adb shell getprop ro.build.version.release | tr -d '\r')"
note "webview: $(adb shell dumpsys package com.google.android.webview | grep -m1 versionName | tr -d ' \r')"

# 1) debug APK (WebView debugging on), camera permission granted at install
adb install -r -g dist/app-debug.apk
adb logcat -c
adb shell am start -W -n "$PKG/.MainActivity"
sleep 8
devtools
node app/ci/cdp-test.mjs "$OUT" debug || RC=1

# 2) the real camera permission dialog: permission taken away, then allowed in the dialog
adb shell pm revoke "$PKG" android.permission.CAMERA
sleep 2
adb shell am start -W -n "$PKG/.MainActivity"
sleep 8
devtools
node app/ci/cdp-test.mjs "$OUT" permission || RC=1
adb exec-out screencap -p > "$OUT/native_debug_end.png"
adb logcat -d > "$OUT/logcat_debug.txt"

# 3) signed release APK: installs, starts, stays running, no crash
adb uninstall "$PKG" >/dev/null
adb logcat -c
if adb install -r dist/app-release.apk; then
  adb shell am start -W -n "$PKG/.MainActivity"
  sleep 12
  adb exec-out screencap -p > "$OUT/native_release_start.png"
  echo "--- processes"; adb shell ps -A | grep -i fruit
  echo "--- activities"; adb shell dumpsys activity activities | grep -E "topResumedActivity|mResumedActivity|ResumedActivity" | head -5
  adb logcat -d > "$OUT/logcat_release.txt"
  echo "--- crash buffer"; adb logcat -d -b crash | tail -40
  echo "--- app log"; grep -iE "fruitslicer|AndroidRuntime|Capacitor|chromium" "$OUT/logcat_release.txt" | tail -40
  if running && ! grep -q "FATAL EXCEPTION" "$OUT/logcat_release.txt"; then
    note "PASS release APK installs, starts and keeps running"
  else
    note "FAIL release APK installs, starts and keeps running"
    RC=1
  fi
else
  note "FAIL release APK installs"
  RC=1
fi
exit $RC
