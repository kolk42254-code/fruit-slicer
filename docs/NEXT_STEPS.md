# Next steps (handoff, 4 Nov 2026)

The owner tested v2.0.0 on the phone and asked for two things:

1. **Better accuracy on the phone.**
2. **More games, not only fruit cutting.** The owner chose all four ideas: Blink Jump, Head Dodge, Balloon Pop
   and Air Draw.

Work in this order: **A (measure, then fix phone accuracy) → release 2.1.0 → B (new games, one at a time)**.
Follow the rules in `CLAUDE.md`: two full test rounds before every release, and simple English for the owner.

---

## What the owner reported

| | |
| --- | --- |
| Phone | Motorola moto g57 power 5G: Snapdragon 6s Gen 4 (4 nm; 4× Cortex-A78 2.4 GHz + 4× A55), Adreno GPU, 8/12 GB RAM, 1080×2400 120 Hz screen, **8 MP f/2.2 1/4" selfie camera**, Android 16 ([GSMArena](https://m.gsmarena.com/motorola_moto_g57_power-ampp-14282.php)) |
| Setup | Phone on a stand ("stander stick"). Distance not known yet. |
| Problems | 1) cursor is slow, behind the finger; 2) cursor jumps or shakes; 3) a swipe goes through a fruit but it does not cut |
| Not asked yet | Website in Chrome or the APK? How far from the phone? Room light? |

---

## A. Phone accuracy

### A1. Build a "Tracking check" screen first (measure before fixing)

> **Status (4 Nov 2026): built, test rounds in progress** (branch `claude/awesome-hawking-1jsm05`; tests:
> `t2_camera.py r1 check,checklayout`, checks in `t2_logic.py`, and a step in `app/ci/cdp-test.mjs`). Not published yet.
> Next: two full test rounds + CI emulator, publish, then the owner sends a report from the phone.
> Notes for reading a report: "Swipes … hand lost X of Y frames" counts tracker results while the fingertip was fast
> (or for 0.25 s after); "broken" = the hand came back later than `CFG.camGap` or was dropped; "Steadiness" = fingertip
> shake while the hand is still (raw tracker point vs. smoothed cursor, in screen pixels); "jumps" = one-frame
> outliers; hand size = longer side of the landmark box ÷ picture width; "sure" = MediaPipe's handedness score.

There is no way to see the phone from here, so the game must show its own numbers.

- Add a button **Settings → "Check hand tracking"**. It opens the camera picture with the **hand skeleton**
  (21 points + bones, both hands), the cursor, and live numbers:
  - camera: resolution and frame rate (`track.getSettings()`), light level (`lastLuma`)
  - tracker: results per second, time per frame (`took`), GPU/CPU, worker/main thread, skipped frames
  - delay: capture → result (`latencyMs`), and whether `captureTime` exists (`rVFC` metadata) or is guessed
  - hand: size in the picture (landmark box width ÷ picture width), presence/handedness score
    (send `res.handedness[i][0].score` from the worker), how many frames lost the hand during the last swipes
  - screen: drawing frames per second
- A **"Copy report"** button (text summary to the clipboard) + the numbers stay on screen for a screenshot.
- Ask the owner to open it on the phone **in Chrome (website) and in the app**, with the phone on the stand where
  they play, then do a few swipes and send a screenshot. Also ask: distance, light, and which one they used before.

### A2. Likely causes on this phone and what to try (confirm each with A1 numbers)

1. **Motion blur → hand lost during a fast swipe → no cut.** A small 1/4" f/2.2 selfie sensor needs long exposures
   indoors, so a fast hand becomes a blur and the tracker drops it.
   - Lower `minHandPresenceConfidence` and `minTrackingConfidence` from 0.5 to about 0.3 (keep detection 0.5) so
     tracking survives blurred frames. Test with `swipe_blur` and a stronger blur (30–45 px).
   - Try a shorter exposure where the camera allows it: `track.getCapabilities()` → if `exposureMode` includes
     `'manual'` and there is an `exposureTime` range, `applyConstraints({advanced: [{exposureMode: 'manual',
     exposureTime: …}]})`. Make it a setting ("Sharper fast moves, darker picture"). Check that the frame rate stays 30.
   - Ask for `frameRate: {ideal: 30, min: 24}` and show the real rate in A1 (some phones drop to 15 fps in dim light).
   - Gap bridging: `CFG.camGap` is 0.3 s. If the hand reappears in line with the swipe, allow up to about 0.45 s.
   - The low-light warning exists (`lightDark`). Tell the owner: bright room, light on the hand.
2. **Lag (cursor behind the finger).**
   - Send smaller frames to the tracker: `createImageBitmap(video, {resizeWidth: 320 or 480, resizeHeight: …,
     resizeQuality: 'low'})` (keep the aspect ratio; landmarks are 0–1 so `toScreen` does not change).
   - Portrait camera: the game asks for no size in portrait (see `startCamera`). Try `width: {ideal: 640},
     height: {ideal: 480}` on the phone and check in A1 that the picture is not cropped square.
   - Draw the cursor ahead by the measured delay using the filtered speed (display only; cap about 80 ms, fade out
     when the hand slows). Cutting already uses real positions with lag compensation.
   - The 120 Hz screen doubles drawing work: on phones, draw at most 60 frames per second.
   - Check that the GPU path works inside the worker on Adreno (OffscreenCanvas WebGL2). If it falls back to CPU and
     is slow, compare with GPU on the main thread.
3. **Jumps and shaking.**
   - The One Euro filter (1.2, 25, 1) was tuned at 30 fps. At lower tracker rates, adapt it, and drop single-frame
     outliers (a point that jumps far and comes back next frame).
   - A hand far from the camera is small and noisy. In A1 show "Come closer" when the hand is under about 12% of the
     picture width. Option: **Zoom** (crop the middle of the camera picture before tracking and show it zoomed,
     e.g. 1.5×) so the hand is bigger for the tracker.
   - A wobbly stand moves the whole picture; tell the owner to keep the stand still.
4. **More forgiving cuts on phones.**
   - Phone fruit are small (`baseR` minimum 34 px). Consider a larger hit radius for camera play on phones, or Easy
     cut sensitivity as the phone default (ask the owner).
   - Test the whole hand as one shape: cut when the area swept between fingertip, knuckles and wrist passes the fruit,
     not only the four points.

### A3. Prove it, then release 2.1.0

- New frame-by-frame tests: tracker at 10 and 15 fps, stronger blur, 150–250 ms delays, outlier frames.
- Two full test rounds + CI emulator → release 2.1.0 (raise versions, see `CLAUDE.md`).
- Ask the owner to try the new version on the phone with the A1 screen and send the report.

---

## B. New games (the owner chose all four)

### Shared work

- **Game hub menu.** Seven targets is too many for slicing on a phone. First menu: Fruit Slicer (opens Classic /
  Arcade / Zen), Blink Jump, Head Dodge, Balloon Pop, Air Draw. Keep "swipe through it or tap it".
- **Face tracking** for Blink Jump and Head Dodge: MediaPipe `FaceLandmarker` from the same `tasks-vision` 1.1.1
  bundle (it has `numFaces`, `outputFaceBlendshapes`, `outputFacialTransformationMatrixes`). Model:
  `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
  (the docs link `…/latest/…`; pin `/1/` and record its SHA-256 the first time CI downloads it, like the hand model).
  Load it only when a face game starts (same download + worker pattern; add face messages to `workerMain`).
  In the app, add it to `prepare-www.mjs` and to the APK content check in the workflow.
- Every game must also work **without the camera** (tap / drag), like fruit cutting does.
- Best score per game, stats, new achievements; new settings (blink sensitivity, head turn or tilt, draw mode).

### B1. Balloon Pop (start here: it uses the hand tracker that already works)

Balloons float up with a wobble. Pop one by touching it with a fingertip of **either hand** (2 hands; index,
middle and thumb tips). No speed is needed, so this suits slower phones. Gold balloon = bonus, spiky balloon = lose a
life (or −10), clock balloon = +5 s. 60 seconds, combos for quick pops.

### B2. Air Draw

A shape appears as a dotted path with a start dot (circle, square, triangle, star, heart, zigzag). Trace it with the
index fingertip. Pen down: **pinch** (thumb tip close to index tip) or **point** (only the index finger out), so ask
the owner which. Score: resample both paths to about 64 points; coverage = share of guide points close to the drawing;
accuracy = average distance. 3 stars for high coverage and low error. Touch drawing as the fallback.

### B3. Blink Jump

A runner moves by itself; obstacles come; **blink to jump**. Use blendshapes `eyeBlinkLeft` and `eyeBlinkRight`:
calibrate 2 s with open eyes (baseline), blink = both above max(0.5, baseline + 0.3) for 2 frames, release below
threshold − 0.15, cooldown about 250 ms, ignore when no face. Keep the jump timing generous (the camera adds delay).
Fallback: tap to jump.

### B4. Head Dodge

Things fall; move a character left/right by **turning the head** (yaw) or **tilting** it (roll), using the facial
transformation matrix. Calibrate the centre at the start; dead zone about ±4°, full width at about ±20°, smoothed.
Optional "look with eyes" mode with `eyeLookIn*/eyeLookOut*` blendshapes (noisier). 3 lives, coins for points.
Fallback: drag.

### B5. Tests for the new games

- Logic tests with injected tracker results: add hooks like `__FS.faceFeed({blinkL, blinkR, yaw, roll}, t)` and a
  hand-landmark feed, then check jumps, dodges, pops, star scores.
- Face pipeline: the `asl.y4m` fake camera has a face, so check the face is found and the head angle is steady.
- Blink: record a short clip of the owner blinking with the laptop webcam (ffmpeg → y4m) for a real check.
- Balloon Pop with two hands: the `two_static` fake camera (two hands).
- Air Draw: synthetic fingertip paths (a perfect circle should score 3 stars, scribbles 0).
- Then two full rounds + CI emulator, release 2.2.0 (or one release per game).

---

## Paste this into Claude Code to start

> Read `CLAUDE.md` and `docs/NEXT_STEPS.md`. Set up the tests with `tests/README.md` and run one round to confirm
> everything passes before changing anything. Then start with step A1 (the Tracking check screen). Explain your steps
> to me point by point in simple English, ask me when something is unclear, and test everything two times before
> publishing.
