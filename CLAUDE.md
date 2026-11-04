# Fruit Slicer: notes for Claude Code

A camera game: slice flying fruit with your hand in the air. One game file runs as a website (GitHub Pages)
and as an Android app (Capacitor). Hand tracking: Google MediaPipe Tasks Vision, on the device.

- Website: https://kolk42254-code.github.io/fruit-slicer/
- Android app: GitHub Releases (v2.0.0 = `FruitSlicer-2.0.0.apk`, 17.7 MB, works offline)
- **Current task: read [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md)** (phone accuracy + 4 new games).

## Working with the owner (Lohi / Akash)

- Explain point by point in simple English. Practical and short. Do not use Kannada.
- Accuracy matters most: check facts on the web or by running code; ask when a request is unclear.
- "Test 2 times": before publishing, run two full test rounds on the final files (plus the CI emulator test).
- The owner plays on a Motorola moto g57 power (Android 16), held on a stand, and on a laptop
  (Lenovo IdeaPad Slim 5, Ryzen 7 7735HS, Windows + Ubuntu).

## Repo map

| Path | What it is |
| --- | --- |
| `src/game.template.html` | **The game source.** HTML + CSS + JS in one file. Fonts are placeholders. |
| `src/fonts/` | Shrikhand + Baloo 2 (OFL), put into the page by the build. |
| `tools/build.py` | Builds `index.html` from the template (`--check` = is it up to date?). |
| `index.html` | **Built output. Never edit by hand.** Served by GitHub Pages and copied into the app. |
| `tools/make_icons.py` | Draws the app icon + start screens with the game's own painters. |
| `tests/` | Test system (Playwright + real Chrome + fake camera videos). See `tests/README.md`. |
| `app/` | Android app (Capacitor 8.5.3). `scripts/prepare-www.mjs` copies the game + tracker + model into `app/www`. |
| `app/android/` | Android project: `MainActivity.java` (Back button, keep screen on, tells the game when the app leaves/returns). |
| `app/ci/` | Emulator tests run by CI (DevTools protocol into the WebView, permission dialog, release APK start). |
| `.github/workflows/android.yml` | Build APK → emulator test → GitHub Release (release only from `main`). |
| `licenses/` | MediaPipe (Apache-2.0), Capacitor (MIT), fonts (OFL). Copied into the app too. |

## Rules

1. Edit `src/game.template.html`, then run `python tools/build.py`. Commit both the template and `index.html`.
2. The website and the app use the same page. The app copy differs only by
   `<meta name="fs-assets" content="local">` (set by `prepare-www.mjs`): the tracker loads from the app's own files.
3. Pinned versions: `@mediapipe/tasks-vision` **1.1.1** (`MP_VERSION` in the template must equal the version in
   `app/package.json`), Capacitor **8.5.3**, hand model `float16/1` (SHA-256 `fbc2a30080c3c557…`).
   For anything loaded from a CDN or npm, use a version that is at least 2 weeks old.
4. Test hooks (`window.__FS`) exist only when the URL ends with `#test`.
5. Never commit `tests/vendor/`, `tests/videos/`, `tests/out/` (downloaded or generated; the LearnOpenCV test photos
   have no stated licence, so they are only used locally).
6. Publishing = pushing to `main` (Pages updates the website; CI builds, tests and releases the APK). Test the app on a
   branch named `app-<something>` first: CI builds and runs the emulator test there without releasing.

## How the game works (src/game.template.html)

The script is one IIFE split into sections by comment lines `// =====…===== <name>` (search for `// ====`):
config, helpers, settings & progress, elements, screen, fruit art, world, effects, rules, achievements, blades,
hand tracker, sound and music, UI, update, render, main loop, wiring (test hooks are at its end), start.

- **States:** `intro → loading → menu → countdown → playing ⇄ paused → over (results)`, plus `error`.
- **Modes:** `MODES` = classic (3 misses), arcade (60 s, power-ups, bomb = −10), zen (90 s, no bombs).
  `DIFF` (easy/normal/hard), `SENS` (cut sensitivity), `POWERS` (freeze 5 s, frenzy 4 s, double 7 s).
- **Blades (all input):** every mouse/touch pointer and every tracked hand point is a "blade".
  Ids: `p<pointerId>`, or `c<handId><t|k|p|w>` for a hand (t = index fingertip, the only point that can set off
  bombs; k = index knuckle, p = pinky knuckle, w = wrist). `bladePoint(id, x, y, t, primary)` measures speed over
  `CFG.speedWindow`; fast enough → `cutAlong(segment, ta, tb)` → `hitTest()`.
- **Lag compensation:** every item keeps a position history (`HIST` = 48 entries). `posAt(item, t)` gives where it
  was when the camera frame was taken. Fruit also count where they are drawn now; bombs only at the frame time.
- **Hand tracker:** `ensureTracker()` downloads 4 files (bundle JS, wasm loader, wasm, model) with one progress bar,
  as Blobs → a Web Worker made from `workerMain` (no network inside the worker). Falls back to the main thread.
  Asset sets: website = jsDelivr → unpkg (code), Google Storage `/1` → `/latest` (model); app = local files first.
  `preferredDelegate()` picks CPU for software GPUs; `tracker.watchdog()` + slow-frame checks restart the worker on CPU.
- **Frame pump:** `requestVideoFrameCallback` (uses `captureTime`) → `processFrame` → `createImageBitmap` → worker →
  `onDetections` → `updateHands` (match hands between frames) → `feedHand` (One Euro filter per point, (1.2, 25, 1)) →
  `bladePoint`. One frame in flight at a time. `pollFrame` is the backup when frame callbacks stall.
- **Camera picture:** `<video id="cam">`, mirrored, `object-fit: cover`; `toScreen()` uses the same cover maths.
  Transparent poster + invisible until the camera is on (Android shows a grey "play" picture otherwise).
- **Leaving:** web `visibilitychange` (camera off after 3 s hidden); app `window.__fsAppHidden(true/false)` from
  `MainActivity.onPause/onResume` (some WebViews never mark the page hidden). The game pauses and frees the camera.
- **Saved on the device:** `localStorage` keys `fruitSlicer.settings` and `fruitSlicer.progress` (stats, achievements,
  blade colour). Version-1 keys are migrated.
- **Tuning knobs:** `CFG` (fruitHit, bombHit 0.9, teleport 0.6, maxSwipe 8, camGap 0.3, gapReset 0.25,
  speedWindow 0.05, comboWindow 0.22, track* matching limits), `SENS`, `CUT_POINTS`, cursor glide in `drawBlades`.
- **Test hooks** (`#test`): `__FS.snap()` (full state), `manual/tick` (controlled clock), `spawn`, `point/end` (fake
  strokes), `feed(image, t)` (run the real tracker on one picture), `feedOnly`, `setVideoSize`, `toScreen`, `posAt`,
  `power`, `setSetting`, `back` (app Back button), `clearItems`, `progress`, `start/menu/pause/resume`.

## Build, test, release

```sh
python tools/build.py                 # template -> index.html (and tests/out/www-app for the app tests)
python tests/get_assets.py            # once: tracker, model, fake-camera videos, ground truth
python tests/run_all.py r1            # one full test round (about 1 hour on a slow machine)
```

Test suites (details in `tests/README.md`): `t2_logic.py` (rules, modes, power-ups, settings, progress, layout;
desktop 1280x720 + phone 412x915), `t2_camera.py` (real tracker with fake camera videos: accuracy, steadiness,
frame-by-frame swipes, offline app files, background thread, slow GPU switch), `t2_errors.py` (camera blocked,
no camera, offline, broken downloads, unplugged camera, app fallbacks), `t2_soak.py` (4 minutes live with camera).
Last results on v2.0.0: round 1 = 279/279, round 2 = 292/292, emulator = 26/26.

**Android app / CI:** push to a branch `app-<name>` → GitHub Actions builds the APK and runs the emulator test
(Android 14, WebView 113). Read results with
`gh api repos/kolk42254-code/fruit-slicer/actions/jobs/<job-id>/logs`; the emulator job prints small screenshots as
base64 JPEG between `SHOT-BEGIN` and `SHOT-END` lines. Artifacts (APKs, screenshots) are also on the run page.

**New release:** raise `version` in `app/package.json` and `versionCode` (+1) and `versionName` in
`app/android/app/build.gradle`, test on an `app-*` branch, then fast-forward `main`. CI publishes `v<version>`.

**Signing:** repository secret `SIGNING_PASSWORD` + `app/signing/release.p12.enc` (encrypted key made by CI on the
first `main` build). The same key must sign every update, so the password must never be lost or changed.

## Known facts

- The cloud test machine is slow (software graphics): the tracker takes 300–600 ms per frame there, so tests check
  correctness frame by frame, not real-time feel. Real phones and laptops are 10–30× faster.
- The emulator's WebView 113 never marks the page hidden when the app goes to the background → `__fsAppHidden`.
- The emulator's launcher sometimes shows "isn't responding"; `app/ci/cdp-test.mjs` taps "Wait".
