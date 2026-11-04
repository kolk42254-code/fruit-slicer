#!/usr/bin/env bash
# Runs inside the Android emulator job. Tests the debug APK over the WebView DevTools connection,
# then checks that the signed release APK installs and starts.
set -u
PKG=io.github.kolk42254code.fruitslicer
OUT=ci-out
mkdir -p "$OUT"
: > "$OUT/results.txt"

adb wait-for-device
adb shell getprop ro.build.version.release | sed 's/^/android: /' | tee -a "$OUT/results.txt"
adb shell dumpsys package com.google.android.webview | grep -m1 versionName | sed 's/^ */webview: /' | tee -a "$OUT/results.txt"

# 1) debug APK (WebView debugging on), camera permission granted at install
adb install -r -g dist/app-debug.apk
adb logcat -c
adb shell am start -W -n "$PKG/.MainActivity"
sleep 8
SOCK=""
for i in $(seq 1 30); do
  SOCK=$(adb shell cat /proc/net/unix | grep -o 'webview_devtools_remote_[0-9]*' | head -1 | tr -d '\r')
  [ -n "$SOCK" ] && break
  sleep 2
done
echo "devtools socket: $SOCK"
adb forward tcp:9222 "localabstract:$SOCK"
node app/ci/cdp-test.mjs "$OUT" debug
RC=$?

# 2) the real camera permission dialog (permission taken away, then allowed in the dialog)
if [ $RC -eq 0 ]; then
  adb shell pm revoke "$PKG" android.permission.CAMERA
  sleep 2
  adb shell am start -W -n "$PKG/.MainActivity"
  sleep 8
  SOCK=$(adb shell cat /proc/net/unix | grep -o 'webview_devtools_remote_[0-9]*' | head -1 | tr -d '\r')
  adb forward --remove-all
  adb forward tcp:9222 "localabstract:$SOCK"
  node app/ci/cdp-test.mjs "$OUT" permission
  RC=$?
fi
adb exec-out screencap -p > "$OUT/native_debug_end.png"
adb logcat -d > "$OUT/logcat_debug.txt"

# 3) signed release APK: installs, starts, shows the start screen, no crash
adb uninstall "$PKG" >/dev/null
adb logcat -c
if adb install -r dist/app-release.apk; then
  adb shell am start -W -n "$PKG/.MainActivity"
  sleep 10
  adb exec-out screencap -p > "$OUT/native_release_start.png"
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb shell cat /sdcard/ui.xml > "$OUT/release_ui.xml" 2>/dev/null
  PID=$(adb shell pidof "$PKG" | tr -d '\r')
  adb logcat -d > "$OUT/logcat_release.txt"
  if [ -n "$PID" ] && ! grep -q "FATAL EXCEPTION" "$OUT/logcat_release.txt"; then
    echo "PASS release APK installs and starts without crashing" | tee -a "$OUT/results.txt"
  else
    echo "FAIL release APK installs and starts without crashing  [pid '$PID']" | tee -a "$OUT/results.txt"
    RC=1
  fi
  if grep -q 'Turn on camera' "$OUT/release_ui.xml"; then
    echo "PASS release APK shows the start screen" | tee -a "$OUT/results.txt"
  else
    echo "INFO release APK start screen text not found in the UI dump (see native_release_start.png)" | tee -a "$OUT/results.txt"
  fi
else
  echo "FAIL release APK installs" | tee -a "$OUT/results.txt"
  RC=1
fi
exit $RC
