#!/usr/bin/env bash
# Runs inside the Android emulator job. Tests the debug APK over the WebView DevTools connection,
# then the real camera-permission dialog, then checks that the signed release APK installs next to it and starts.
set -u
PKG=io.github.kolk42254code.fruitslicer                    # release APK ("Fruit Slicer")
TEST_PKG=$PKG.test                                        # debug APK ("Fruit Slicer TEST"): own ID, installs next to the real app
ACTIVITY=io.github.kolk42254code.fruitslicer.MainActivity  # the activity class keeps this name in both
TEST_CERT=5b3869129f4e9353484721b75aba69aa44c6c1dd5c2f99ba4e487dfc6fb71ae7  # app/android/test-debug.keystore (SHA-256)
OUT=ci-out
mkdir -p "$OUT"
: > "$OUT/results.txt"
RC=0

note() { echo "$1" | tee -a "$OUT/results.txt"; }
running() { adb shell ps -A -o NAME 2>/dev/null | tr -d '\r' | grep -qx "$1"; }
installed() { adb shell pm list packages 2>/dev/null | tr -d '\r' | grep -qx "package:$1"; }
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

# 0) the two APKs: test app has its own ID and name, the release keeps the real ones
BT="$(ls -d "${ANDROID_HOME:-/nonexistent}"/build-tools/* 2>/dev/null | sort -V | tail -1)"
if [ -n "$BT" ] && [ -x "$BT/aapt2" ]; then
  DBG="$("$BT/aapt2" dump badging dist/app-debug.apk 2>/dev/null)"
  REL="$("$BT/aapt2" dump badging dist/app-release.apk 2>/dev/null)"
  echo "$DBG" | grep -E "^package:|application-label:|launchable-activity:"
  echo "$REL" | grep -E "^package:|application-label:|launchable-activity:"
  if echo "$DBG" | grep -q "^package: name='$TEST_PKG'" && echo "$DBG" | grep -q "launchable-activity: name='$ACTIVITY'.*label='Fruit Slicer TEST'" \
     && echo "$REL" | grep -q "^package: name='$PKG'" && echo "$REL" | grep -q "launchable-activity: name='$ACTIVITY'.*label='Fruit Slicer'"; then
    note "PASS debug APK is $TEST_PKG named \"Fruit Slicer TEST\"; release APK is $PKG named \"Fruit Slicer\""
  else
    note "FAIL debug APK is $TEST_PKG named \"Fruit Slicer TEST\"; release APK is $PKG named \"Fruit Slicer\""
    RC=1
  fi
else
  note "note: aapt2 not found, APK names not checked"
fi
if [ -n "$BT" ] && [ -x "$BT/apksigner" ]; then
  CERT="$("$BT/apksigner" verify --print-certs dist/app-debug.apk 2>/dev/null | grep -m1 'certificate SHA-256 digest' | awk '{print $NF}')"
  if [ "$CERT" = "$TEST_CERT" ]; then
    note "PASS debug APK is signed with the fixed test key (new TEST builds install over old ones)"
  else
    note "FAIL debug APK is signed with the fixed test key (got: ${CERT:-none})"
    RC=1
  fi
fi

# 1) debug APK (WebView debugging on), camera permission granted at install
adb install -r -g dist/app-debug.apk
adb logcat -c
adb shell am start -W -n "$TEST_PKG/$ACTIVITY"
sleep 8
devtools
node app/ci/cdp-test.mjs "$OUT" debug || RC=1

# 2) the real camera permission dialog: permission taken away, then allowed in the dialog
adb shell pm revoke "$TEST_PKG" android.permission.CAMERA
sleep 2
adb shell am start -W -n "$TEST_PKG/$ACTIVITY"
sleep 8
devtools
node app/ci/cdp-test.mjs "$OUT" permission || RC=1
adb exec-out screencap -p > "$OUT/native_debug_end.png"
adb logcat -d > "$OUT/logcat_debug.txt"

# 3) signed release APK: installs next to the test app (still installed), starts, stays running, no crash
adb shell am force-stop "$TEST_PKG"
adb logcat -c
if adb install -r dist/app-release.apk; then
  if installed "$TEST_PKG" && installed "$PKG"; then
    note "PASS release app installs next to the test app (both installed)"
  else
    note "FAIL release app installs next to the test app (both installed)"
    RC=1
  fi
  adb shell am start -W -n "$PKG/$ACTIVITY"
  sleep 12
  adb exec-out screencap -p > "$OUT/native_release_start.png"
  echo "--- processes"; adb shell ps -A | grep -i fruit
  echo "--- activities"; adb shell dumpsys activity activities | grep -E "topResumedActivity|mResumedActivity|ResumedActivity" | head -5
  adb logcat -d > "$OUT/logcat_release.txt"
  echo "--- crash buffer"; adb logcat -d -b crash | tail -40
  echo "--- app log"; grep -iE "fruitslicer|AndroidRuntime|Capacitor|chromium" "$OUT/logcat_release.txt" | tail -40
  if running "$PKG" && ! grep -q "FATAL EXCEPTION" "$OUT/logcat_release.txt"; then
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
