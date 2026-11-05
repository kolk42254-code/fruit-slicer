# Tests

The tests open the game in a real Chrome/Chromium with Playwright. The camera is faked with video files
(`--use-fake-device-for-media-stream`), and the CDN, model and font addresses are answered from local copies, so
the tests need no internet once set up. The hand tracker is the real MediaPipe code; correct answers come from
Python MediaPipe (independent of the game).

## Set up (once)

Ubuntu is easiest. Windows works too if `ffmpeg` and `node` are on PATH.

```sh
python -m pip install -r tests/requirements.txt
python -m playwright install chromium   # skip if Google Chrome is installed (it is used when found)
# also needed: ffmpeg (sudo apt install ffmpeg) and Node 22 (for the syntax check and the app)
python tools/build.py                   # builds index.html + tests/out/www-app
python tests/get_assets.py              # downloads into tests/vendor, builds tests/videos (about 280 MB, not committed)
```

`get_assets.py` downloads `@mediapipe/tasks-vision` 1.1.1 from npm, the official hand model (checked by SHA-256),
and two test files from the LearnOpenCV HandPose folder on GitHub (`front-back.jpg`, `asl.mp4`). It then builds the
fake-camera videos with `make_videos.py` and the ground truth (`videos/gt.json`, `videos/swipe_landmarks.json`).

## Run

```sh
python tests/run_all.py r1          # one full round: build check, JS syntax, logic, camera, errors, 4-min soak
python tests/run_all.py r2 --quick  # without the soak
```

Logs and screenshots go to `tests/out/` (`r1_logic.log`, `r1_1280x720_menu.png`, …). Single suites:

| Command | What it checks |
| --- | --- |
| `python t2_logic.py r1 [desktop\|phone]` | rules, modes, power-ups, settings, progress, layout, pause/back, soak with a bot (controlled clock) |
| `python t2_camera.py r1 [static,two,hands,portrait,nohand,dark,asl,feed_sharp,feed_blur,feed_slow,feed_slow1,gpu,speed,lead,exposure,noworker,nofileflag,app,live,check,checklayout]` | real tracker: cursor on the fingertip (< 8 px), steadiness, swipes frame by frame, 1 or 2 hands, GPU/CPU speed test, cursor lead, camera exposure (simulated camera controls), offline app files, the tracking check screen (numbers, skeleton, report copy, phone layout) |
| `python t2_errors.py r1` | blocked/missing camera, offline, broken downloads, unplugged camera, app fallbacks |
| `python t2_soak.py 4 r1` | 4 minutes live with the camera: frame rate, memory, tracker keeps answering |
| `python shots_v2.py` | screenshots of every panel at 4 screen sizes |

Run them from the `tests` folder (or use `run_all.py`). Settings: `GAME_FILE` (page to test), `CHROME_PATH`.

## Notes

- On a slow or software-graphics machine the tracker takes 300–600 ms per frame. The tests allow for that; they check
  correctness, not speed. Use `t2_soak.py` and the in-game numbers to judge speed on real devices.
- Do not commit `tests/vendor`, `tests/videos` or `tests/out` (see `.gitignore`).
- The Android emulator tests are in `app/ci/` and run in GitHub Actions (`.github/workflows/android.yml`).
