# Fruit Slicer

A camera game: slice flying fruit with your hand in the air. Avoid the bombs.

- **Play in the browser:** https://kolk42254-code.github.io/fruit-slicer/
- **Android app:** download the latest `FruitSlicer-….apk` from the [Releases page](https://github.com/kolk42254-code/fruit-slicer/releases/latest). The app works with no internet.

## How to play

1. Open the game (Chrome or Edge on a laptop, Chrome on a phone, or the Android app).
2. Tap **Turn on camera** and allow the camera.
3. Stand the device up about an arm's length away, in a bright room.
4. Swipe your hand through a fruit to choose a game.

No camera? Choose **Play with mouse or touch**.

### Game modes

| Mode | Rules |
| --- | --- |
| Classic | 3 missed fruit or bombs and the game ends. |
| Arcade | 60 seconds with power-ups. A bomb takes 10 points. |
| Zen | 90 seconds, no bombs. Relax and slice. |

### Power-ups (Arcade)

Slice the glowing bananas:

- **Freeze** (blue): everything slows down and the clock stops for 5 seconds.
- **Frenzy** (orange): fruit flies in from both sides for 4 seconds.
- **Double** (yellow): every slice counts twice for 7 seconds.

Slicing 3 or more fruit in one swipe gives a combo bonus.

### Settings

Difficulty, cut sensitivity, cutting with the whole hand or only the fingertip, camera picture on or off,
and sound and music volume. Bombs only go off from your fingertip.

### Progress

Your stats, best scores, 12 achievements and 7 blade colours to unlock are saved on your device.

## Install the Android app

1. On your phone, open the [Releases page](https://github.com/kolk42254-code/fruit-slicer/releases/latest) and download the `.apk` file.
2. Open it. If Android asks, allow installing apps from your browser or Files app.
3. Open **Fruit Slicer**, tap **Turn on camera** and choose **Allow**.

## Privacy

The camera picture stays on your device. Hand tracking runs on the device with Google MediaPipe; nothing is uploaded.
In the browser, the first start downloads the hand tracker (about 22 MB) and the browser keeps it after that.
The Android app has the hand tracker built in. The app turns the camera off when you leave it.

## For developers

| Path | What it is |
| --- | --- |
| `index.html` | The whole game in one file (served by GitHub Pages). |
| `app/` | The Android app, made with [Capacitor](https://capacitorjs.com/). It wraps `index.html`. |
| `app/scripts/prepare-www.mjs` | Copies the game and the hand tracker (code + model) into the app, so it runs offline. |
| `app/android/` | The Android project (icon, start screen, Back button, keep-screen-on). |
| `app/ci/` | Emulator tests that run on every build. |
| `.github/workflows/android.yml` | Builds the APK, tests it on an Android emulator, and publishes it on the Releases page. |

The APK is built by GitHub Actions. Every push to `main` that changes the game or the app builds, tests and releases a
new APK. To make a new version, raise `version` in `app/package.json` and `versionCode`/`versionName` in
`app/android/app/build.gradle`.

**Signing:** add a repository secret named `SIGNING_PASSWORD` (Settings → Secrets and variables → Actions). On the first
build the workflow makes the app's signing key and saves only an encrypted copy (`app/signing/release.p12.enc`). Keep the
password safe: the same key is needed to publish updates that install over the old app. Without the secret, each build
uses a one-time key, and updating then needs an uninstall first.

Build locally (needs Node 22, Java 21 and the Android SDK):

```sh
cd app
npm ci
node scripts/prepare-www.mjs
npx cap sync android
cd android && ./gradlew assembleDebug
```

## Credits

- Hand tracking: [MediaPipe Tasks Vision](https://www.npmjs.com/package/@mediapipe/tasks-vision) 1.1.1 and the hand landmarker model by Google (Apache License 2.0).
- App wrapper: [Capacitor](https://capacitorjs.com/) 8 (MIT License).
- Fonts: [Shrikhand](https://fonts.google.com/specimen/Shrikhand) by Jonny Pinhorn and [Baloo 2](https://fonts.google.com/specimen/Baloo+2) by Ek Type (SIL Open Font License 1.1), built into the page.
- Fruit art, sounds and music are drawn and made in code by the game.

The licence texts are in the [`licenses`](licenses) folder (and inside the app).
