"""Suite B (v2): the real hand tracker, running in its background thread.
Mapping accuracy, still-hand steadiness, two hands, phone portrait, no hand, real webcam clip, dark room,
frame-by-frame swipes (sharp, blurred, slow tracker) with whole-hand and fingertip cutting, slow-GPU switch,
main-thread fallback, the offline app files, a file opened straight from disk, and the tracking check screen
(its numbers, skeleton, report copy, and layout on phones)."""
import asyncio, json, math, os, pathlib, sys, time
from playwright.async_api import async_playwright
from harness import *

TAG = sys.argv[1] if len(sys.argv) > 1 else 'r1'
ONLY = sys.argv[2].split(',') if len(sys.argv) > 2 else None
# Ground truth = Python MediaPipe on the first frame of each fake-camera video (independent of the game).
# tests/get_assets.py writes videos/gt.json; the numbers below are the values measured when the suite was written.
GT = {'static_one': [(409.7, 175.5)], 'two_static': [(204.3, 77.9), (445.4, 83.5)], 'portrait_one': [(261.1, 244.6)]}
if os.path.exists(os.path.join(VIDEOS, 'gt.json')):
    GT = {k: [tuple(p) for p in v] for k, v in json.load(open(os.path.join(VIDEOS, 'gt.json'))).items()}
VSIZE = {'static_one': (640, 480), 'two_static': (640, 480), 'portrait_one': (480, 640)}
LM = json.load(open(os.path.join(VIDEOS, 'swipe_landmarks.json')))      # Python MediaPipe: wrist 0, knuckles 5/17, tip 8 on swipe frames
MP_NOISE = ('gl_context.cc', 'landmark_projection_calculator', 'inference_feedback_manager', 'XNNPACK')


def expected_screen(vx, vy, vw, vh, W, H):
    s = max(W / vw, H / vh); dw, dh = vw * s, vh * s
    ox, oy = (W - dw) / 2, (H - dh) / 2
    return (W - (ox + vx * s), oy + vy * s)       # picture is mirrored like a mirror

async def start_camera(page, timeout=180000):
    await page.click('#btn-camera')
    await wait_state(page, 'menu', timeout=timeout)

async def poll_hands(page, secs, every=0.25):
    out = []
    t_end = time.time() + secs
    while time.time() < t_end:
        s = await snap(page)
        out.append(s['hands'])
        await page.wait_for_timeout(int(every * 1000))
    return out

async def mapping_case(p, R, video, W, H, mobile):
    br = await launch(p, video=video)
    ctx, page = await open_game(br, Net(), W, H, mobile=mobile, dpr=1)
    await start_camera(page)
    await page.wait_for_timeout(3000)
    samples = await poll_hands(page, 5)
    s = await snap(page)
    vw, vh = VSIZE[video]
    R.check(f'[{video} {W}x{H}] camera frames are {vw}x{vh}; tracker in background thread', (s['video']['w'], s['video']['h']) == (vw, vh) and s['trackerKind'] == 'worker', f"{s['video']} {s['trackerKind']}")
    R.check(f'[{video}] camera picture shown once the camera is on', await page.evaluate("getComputedStyle(document.getElementById('cam')).opacity") == '1')
    exp = [expected_screen(x, y, vw, vh, W, H) for x, y in GT[video]]
    last = samples[-1]
    R.check(f'[{video}] tracks {len(exp)} hand(s)', len(last) == len(exp), f'{len(last)} found')
    errs = []
    for ex, ey in exp:
        if not last:
            errs.append(999); continue
        h = min(last, key=lambda h: math.hypot(h['sx'] - ex, h['sy'] - ey))
        errs.append(math.hypot(h['sx'] - ex, h['sy'] - ey))
    R.check(f'[{video}] finger cursor lands on the real fingertip (< 8 px)', all(e < 8 for e in errs), 'errors px: ' + ', '.join(f'{e:.1f}' for e in errs) + ' | expected ' + ', '.join(f'({x:.0f},{y:.0f})' for x, y in exp))
    xs = [hs[0]['dx'] for hs in samples if hs and hs[0]['dx'] is not None]; ys = [hs[0]['dy'] for hs in samples if hs and hs[0]['dy'] is not None]
    if len(xs) > 3:
        jx = max(xs) - min(xs); jy = max(ys) - min(ys)
        R.check(f'[{video}] drawn cursor is steady while the hand is still (< 6 px wobble)', jx < 6 and jy < 6, f'x range {jx:.1f}px, y range {jy:.1f}px over {len(xs)} samples')
    R.check(f'[{video}] chip says hand found', 'Hand found' in s['ui']['chipText'] and s['ui']['chip'], s['ui']['chipText'])
    await page.screenshot(path=f'{OUT}/{TAG}_cam_{video}_menu.png')
    if video == 'static_one':
        # a still hand resting on fruit (fingertip, knuckle, wrist) for ~8 s must never cut
        await page.evaluate("__FS.spawning(false)")
        await page.evaluate("__FS.start('classic')")
        await wait_state(page, 'playing', timeout=30000)
        h = (await snap(page))['hands'][0]
        pts = h['pts']
        for suf, typ in (('t', 'watermelon'), ('k', 'orange'), ('w', 'lemon')):
            if pts.get(suf):
                await page.evaluate(f"__FS.spawn({{type:'{typ}', x:{pts[suf][0]}, y:{pts[suf][1]}, frozen:true}})")
        await page.wait_for_timeout(8000)
        s = await snap(page)
        R.check('[static_one] still hand on 3 fruit (fingertip, knuckle, wrist) for 8 s cuts nothing', len(s['items']) == 3 and s['score'] == 0,
                f"fastest still-finger speed {s['stats'].get('camSpeedMax', 0)} px/s vs cut speed {0.6 * s['MIN']:.0f} px/s, detections {s['detectCount']}, points {pts}")
        R.check('[static_one] no "show your hand" or "too dark" hint while the hand is visible in a bright room', not s['ui']['hint'] and not s['ui']['lightHint'], f"luma {s['luma']}")
        await page.screenshot(path=f'{OUT}/{TAG}_cam_static_playing.png')
        # web: a quick look at another tab keeps the camera on; 3 s away turns it off; coming back turns it on
        await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))""")
        await page.wait_for_timeout(1000)
        await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))""")
        s1 = await snap(page)
        await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))""")
        await page.wait_for_timeout(3600)
        s2 = await snap(page)
        await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))""")
        await page.wait_for_timeout(4000)
        s3 = await snap(page)
        R.check('[static_one] tab away for 1 s keeps the camera; 3 s away turns it off; back turns it on and tracks',
                s1['camTracks'] == 1 and s2['camTracks'] == 0 and s3['camTracks'] == 1 and len(s3['hands']) == 1, f"{s1['camTracks']} {s2['camTracks']} {s3['camTracks']} hands {len(s3['hands'])}")
        await page.evaluate("__FS.resume()")
        await page.evaluate("__FS.setSetting('camView', 'hide')")
        await page.wait_for_timeout(1500)
        s2 = await snap(page)
        R.check('[static_one] hiding the camera picture keeps tracking', s2['ui']['camHidden'] and len(s2['hands']) == 1 and s2['handsSeenAgo'] < 2)
        await page.screenshot(path=f'{OUT}/{TAG}_cam_hidden_playing.png')
    R.check(f'[{video}] tracker running on {s["delegate"]}, avg {s["detectMs"]} ms per frame here, page {s["fps"]} fps', s['delegate'] in ('CPU', 'GPU') and not s['trackingDead'], s['gpuName'][:60])
    bad = problems(page, allow=MP_NOISE)
    R.check(f'[{video}] console clean (MediaPipe info lines ignored)', not bad, ' | '.join(bad[:3]))
    await br.close()

async def nohand_case(p, R):
    br = await launch(p, video='nohand')
    ctx, page = await open_game(br, Net(), 1280, 720)
    await start_camera(page)
    samples = await poll_hands(page, 5)
    s = await snap(page)
    R.check('[nohand] empty room: no hand, no cursor', all(len(x) == 0 for x in samples))
    R.check('[nohand] chip asks to show a hand', 'Looking for your hand' in s['ui']['chipText'], s['ui']['chipText'])
    await page.evaluate("__FS.start('classic')")
    await wait_state(page, 'playing', timeout=30000)
    await page.wait_for_timeout(2500)
    s = await snap(page)
    R.check('[nohand] during play, "Show your hand" hint appears', s['ui']['hint'])
    await page.screenshot(path=f'{OUT}/{TAG}_cam_nohand_hint.png')
    await br.close()

async def dark_case(p, R):
    br = await launch(p, video='dark_one')
    ctx, page = await open_game(br, Net(), 1280, 720)
    await start_camera(page)
    await page.wait_for_timeout(4500)
    s = await snap(page)
    R.check('[dark room] menu warns the room is too dark', s['ui']['lightChip'] and s['dark'], f"luma {s['luma']}")
    await page.screenshot(path=f'{OUT}/{TAG}_cam_dark_menu.png')
    await page.evaluate("__FS.start('zen')")
    await wait_state(page, 'playing', timeout=30000)
    await page.wait_for_timeout(1000)
    s = await snap(page)
    R.check('[dark room] the warning stays during play', s['ui']['lightHint'])
    bad = problems(page, allow=MP_NOISE)
    R.check('[dark room] console clean', not bad, ' | '.join(bad[:3]))
    await br.close()

async def asl_case(p, R):
    br = await launch(p, video='asl')
    ctx, page = await open_game(br, Net(), 1280, 720)
    await start_camera(page)
    found = None
    t_end = time.time() + 15
    while time.time() < t_end:
        s = await snap(page)
        if s['hands']:
            found = s; break
        await page.wait_for_timeout(150)
    R.check('[asl] real webcam clip: hand found next to a face', found is not None)
    if found:
        vw, vh = found['video']['w'], found['video']['h']
        h0 = found['hands'][0]
        ex, ey = expected_screen(h0['rx'] * vw, h0['ry'] * vh, vw, vh, 1280, 720)
        R.check('[asl] cursor matches the detected fingertip on screen (independent formula)', math.hypot(ex - h0['sx'], ey - h0['sy']) < 40,
                f"cursor ({h0['sx']:.0f},{h0['sy']:.0f}) vs ({ex:.0f},{ey:.0f}), video {vw}x{vh}")
        await page.screenshot(path=f'{OUT}/{TAG}_cam_asl_hand.png')
    await br.close()

FEED_JS_TEMPLATE = """async ([name, frames, from, to, fps, stride]) => {
  stride = stride || 1;
  window.__imgs = window.__imgs || {};
  if (!window.__imgs[name]) {
    window.__imgs[name] = await Promise.all(Array.from({length: frames}, (_, i) => new Promise((res, rej) => {
      const im = new Image(); im.onload = () => res(im); im.onerror = rej;
      im.src = '__FRAMES_URL__' + name + '/f' + String(i + 1).padStart(3, '0') + '.png';
    })));
  }
  const imgs = window.__imgs[name], log = [];
  for (let i = from; i <= to; i += stride) {
    const tips = await __FS.feed(imgs[i], __FS.now());
    const s = __FS.snap();
    log.push({ f: i, tips: tips ? tips.length : -1, hands: s.hands.map(h => [Math.round(h.sx), Math.round(h.sy)]), score: s.score, items: s.items.length, lives: s.lives });
    __FS.tick(stride / fps, 1);
  }
  return log;
}"""

FEED_JS = FEED_JS_TEMPLATE.replace('__FRAMES_URL__', pathlib.Path(VIDEOS, 'frames').resolve().as_uri() + '/')

def screen_pt(frame, idx, W=1280, H=720):
    x, y = LM[str(frame)][str(idx)]
    return expected_screen(x, y, 640, 480, W, H)

async def feed_case(p, R, name):
    meta = json.load(open(f'{VIDEOS}/meta.json'))[name]
    W, H = 1280, 720
    br = await launch(p, video='nohand')
    ctx, page = await open_game(br, Net(), W, H)
    await start_camera(page)
    await page.evaluate("__FS.feedOnly(true); __FS.setVideoSize(640, 480); __FS.manual(true); __FS.spawning(false); __FS.start('classic'); __FS.tick(1/60, 120)")
    s = await snap(page)
    assert s['state'] == 'playing'
    y_path = expected_screen(0, meta['tip_y'], 640, 480, W, H)[1]
    x_left = expected_screen(meta['tip_x_left'], 0, 640, 480, W, H)[0]     # hand at video-left = screen right
    x_right = expected_screen(meta['tip_x_right'], 0, 640, 480, W, H)[0]
    knuckle_y = (screen_pt(1, 5)[1] + screen_pt(1, 17)[1]) / 2               # palm path (index + pinky knuckles)
    print(f'   [{name}] fingertip path y {y_path:.0f}, palm path y {knuckle_y:.0f}, finger moves on screen from x {x_left:.0f} to {x_right:.0f}')
    # 1) still hand: fruit under the fingertip and under the knuckles (hold frames 0-17, played twice = 1.2 s)
    tip0 = screen_pt(1, 8); k0 = screen_pt(1, 5)
    await page.evaluate(f"__FS.spawn({{type:'orange', x:{tip0[0]}, y:{tip0[1]}, frozen:true}})")
    await page.evaluate(f"__FS.spawn({{type:'lemon', x:{k0[0]}, y:{k0[1]}, frozen:true}})")
    log = await page.evaluate(FEED_JS, [name, meta['frames'], 0, 17, 30])
    log += await page.evaluate(FEED_JS, [name, meta['frames'], 0, 17, 30])
    s = await snap(page)
    ys = [h[0][1] for h in (l['hands'] for l in log) if h]
    xs = [h[0][0] for h in (l['hands'] for l in log) if h]
    R.check(f'[{name}] finger tracked on all still frames', all(l['tips'] == 1 for l in log), f"{sum(l['tips'] == 1 for l in log)}/{len(log)}")
    R.check(f'[{name}] cursor on the true fingertip during the hold (< 8 px)', xs and abs(sum(xs) / len(xs) - x_left) < 8 and abs(sum(ys) / len(ys) - y_path) < 8, f'avg ({sum(xs)/len(xs):.0f},{sum(ys)/len(ys):.0f}) vs ({x_left:.0f},{y_path:.0f})')
    R.check(f'[{name}] still hand on fruit (fingertip + knuckle) does not cut (30 fps timing)', s['score'] == 0 and len(s['items']) == 2, f"max still speed {s['stats'].get('camSpeedMax', 0)} px/s, cut needs {0.6 * s['MIN']:.0f}")
    await page.evaluate("__FS.start('classic'); __FS.tick(1/60, 120); __FS.spawning(false)")
    # 2) fast swipe across: whole-hand cutting (default)
    mid = (x_left + x_right) / 2
    bomb_x = x_right + (x_left - x_right) * 0.78
    plan = [('A on fingertip path', 'apple', mid, y_path, True), ('B on fingertip path', 'apple', x_right + (x_left - x_right) * 0.25, y_path, True),
            ('K on palm path', 'apple', mid, knuckle_y, True), ('C above the path', 'apple', mid - 120, y_path - 150, False),
            ('D beyond the end', 'apple', x_right - 160, y_path, False), ('bomb on palm path', 'bomb', bomb_x, knuckle_y, False)]
    for _, typ, x, y, _ in plan:
        spec = "{kind:'bomb'" if typ == 'bomb' else f"{{type:'{typ}'"
        await page.evaluate(f"__FS.spawn({spec}, x:{x}, y:{y}, frozen:true}})")
    ids = [i['id'] for i in (await snap(page))['items']]
    log = await page.evaluate(FEED_JS, [name, meta['frames'], 10, 30, 30])
    s = await snap(page)
    left = {i['id'] for i in s['items']}
    for (label, typ, x, y, should_cut), iid in zip(plan, ids):
        cut = iid not in left
        R.check(f'[{name}] whole hand: {label} {"cut" if should_cut else "not cut"}', cut == should_cut, f'at ({x:.0f},{y:.0f})')
    R.check(f'[{name}] whole hand: 3 fruit in one swipe = combo (+3), no life lost', s['score'] == 6 and s['lives'] == 3, f"score {s['score']}, lives {s['lives']}")
    moving = [l for l in log if 18 <= l['f'] <= 25]
    R.check(f'[{name}] hand found on fast-moving frames', sum(l['tips'] for l in moving) >= 6, f"{sum(l['tips'] for l in moving)}/8 moving frames tracked: " + str([l['hands'] for l in moving]))
    # 3) swipe back: a new fruit on the path is cut
    await page.evaluate(f"__FS.spawn({{type:'kiwi', x:{mid + 60}, y:{y_path}, frozen:true}})")
    await page.evaluate(FEED_JS, [name, meta['frames'], 31, 51, 30])
    s = await snap(page)
    R.check(f'[{name}] swipe back cuts the fruit on the path', s['score'] == 7 and s['lives'] == 3, f"score {s['score']}")
    await page.screenshot(path=f'{OUT}/{TAG}_feed_{name}.png')
    # 4) fingertip-only setting: the palm no longer cuts
    await page.evaluate("__FS.setSetting('cutWith', 'finger')")
    await page.evaluate(f"__FS.spawn({{type:'mango', x:{mid}, y:{y_path}, frozen:true}})")
    await page.evaluate(f"__FS.spawn({{type:'mango', x:{mid + 40}, y:{knuckle_y}, frozen:true}})")
    ids2 = [i['id'] for i in (await snap(page))['items']][-2:]
    await page.evaluate(FEED_JS, [name, meta['frames'], 10, 30, 30])
    s = await snap(page)
    left = {i['id'] for i in s['items']}
    R.check(f'[{name}] fingertip only: fruit on the fingertip path cut, fruit on the palm path not cut', ids2[0] not in left and ids2[1] in left and s['score'] == 8, f"score {s['score']}")
    await page.evaluate("__FS.setSetting('cutWith', 'hand')")
    errs = await page.evaluate('window.__FS_ERRORS || []')
    R.check(f'[{name}] no frame errors', not errs, str(errs[:2]))
    await br.close()

async def feed_slow_case(p, R, name):
    meta = json.load(open(f'{VIDEOS}/meta.json'))[name]
    W, H = 1280, 720
    br = await launch(p, video='nohand')
    ctx, page = await open_game(br, Net(), W, H)
    await start_camera(page)
    await page.evaluate("__FS.feedOnly(true); __FS.setVideoSize(640, 480); __FS.manual(true); __FS.spawning(false); __FS.start('classic'); __FS.tick(1/60, 120)")
    y_path = expected_screen(0, meta['tip_y'], 640, 480, W, H)[1]
    x_left = expected_screen(meta['tip_x_left'], 0, 640, 480, W, H)[0]
    x_right = expected_screen(meta['tip_x_right'], 0, 640, 480, W, H)[0]
    mid = (x_left + x_right) / 2
    await page.evaluate(f"__FS.spawn({{type:'mango', x:{mid}, y:{y_path}, frozen:true}})")
    await page.evaluate(f"__FS.spawn({{type:'lemon', x:{mid}, y:{y_path - 160}, frozen:true}})")
    await page.evaluate(f"__FS.spawn({{kind:'bomb', x:{mid - 60}, y:{y_path}, frozen:true}})")
    log = await page.evaluate(FEED_JS, [name, meta['frames'], 2, 30, 30, 4])
    s = await snap(page)
    R.check(f'[{name} @7.5fps] slow tracker: fruit on the swipe path is cut, fruit off the path stays', s['score'] == 1 and any(i['type'] == 'lemon' for i in s['items']),
            f"score {s['score']}, samples " + str([(l['f'], l['hands']) for l in log]))
    R.check(f'[{name} @7.5fps] slow tracker: a bomb on the fingertip path still goes off', s['lives'] == 2, f"lives {s['lives']}")
    await br.close()

async def gpu_switch_case(p, R):
    br = await launch(p, video='static_one')
    ctx, page = await open_game(br, Net(), 1280, 720, init_js="window.__FS_DELEGATE = 'GPU'")
    await start_camera(page)
    t0 = time.time(); t_end = t0 + 90
    s = await snap(page)
    while time.time() < t_end and s['delegate'] != 'CPU':
        await page.wait_for_timeout(1000)
        s = await snap(page)
    R.check('[slow GPU] slow GPU tracker (background thread) switches itself to CPU', s['delegate'] == 'CPU' and s['slowGpuSwitch'] and s['trackerKind'] == 'worker', f"after {time.time() - t0:.0f}s")
    await page.wait_for_timeout(6000)
    s = await snap(page)
    R.check('[slow GPU] hand still tracked after the switch', len(s['hands']) == 1 and s['handsSeenAgo'] < 2 and not s['trackingDead'], json.dumps(s['hands'])[:200])
    await br.close()

async def noworker_case(p, R):
    br = await launch(p, video='static_one')
    ctx, page = await open_game(br, Net(), 1280, 720, init_js="window.__FS_NO_WORKER = true")
    await start_camera(page)
    await page.wait_for_timeout(5000)
    s = await snap(page)
    exp = expected_screen(*GT['static_one'][0], 640, 480, 1280, 720)
    ok = s['hands'] and math.hypot(s['hands'][0]['sx'] - exp[0], s['hands'][0]['sy'] - exp[1]) < 8
    R.check('[no background thread] falls back to the main thread and still tracks accurately', s['trackerKind'] == 'main' and ok, f"{s['trackerKind']} {s['hands'][:1]}")
    bad = problems(page, allow=MP_NOISE)
    R.check('[no background thread] console clean', not bad, ' | '.join(bad[:3]))
    await br.close()

async def nofileflag_case(p, R):
    br = await launch(p, video='static_one', file_access=False)
    ctx, page = await open_game(br, Net(), 1280, 720)
    await start_camera(page)
    await page.wait_for_timeout(5000)
    s = await snap(page)
    R.check('[downloaded file, normal Chrome] background tracker works from a file on disk', s['trackerKind'] == 'worker' and len(s['hands']) == 1, f"{s['trackerKind']} hands {len(s['hands'])}")
    await br.close()

async def app_case(p, R):
    base, srv = serve_dir(prepare_www_app())
    br = await launch(p, video='static_one')
    net = Net(block_cdn=True, block_model=True, local_base=base)
    ctx, page = await open_game(br, net, 412, 915, mobile=True, url=base + 'index.html')
    s = await snap(page)
    R.check('[app files] intro says it runs offline', 'offline' in s['ui']['introNote'], s['ui']['introNote'])
    await start_camera(page, timeout=120000)
    await page.wait_for_timeout(4000)
    s = await snap(page)
    exp = expected_screen(*GT['static_one'][0], 640, 480, 412, 915)
    R.check('[app files] hand tracker loads from the app itself (internet blocked)', s['trackerSource'] == 'local' and s['trackerKind'] == 'worker' and len(s['hands']) == 1, f"{s['trackerSource']} {s['trackerKind']}")
    online = [u for u in net.log if u.startswith('https://')]
    R.check('[app files] no internet requests at all', not online, str(online[:3]))
    await page.screenshot(path=f'{OUT}/{TAG}_cam_app_menu.png')
    # the Android app tells the page when it leaves the screen (some WebViews never mark the page hidden)
    await page.evaluate("__FS.start('zen')")
    await wait_state(page, 'playing', timeout=30000)
    await page.evaluate("window.__fsAppHidden(true)")
    s = await snap(page)
    R.check('[app files] app leaving the screen (Android hook) pauses and turns the camera off', s['state'] == 'paused' and s['camTracks'] == 0 and s['camAsleep'], f"tracks {s['camTracks']}")
    await page.evaluate("window.__fsAppHidden(false)")
    await page.wait_for_timeout(4000)
    s = await snap(page)
    R.check('[app files] app coming back (Android hook) turns the camera on and finds the hand', s['camTracks'] == 1 and len(s['hands']) == 1 and s['state'] == 'paused', f"tracks {s['camTracks']}, hands {len(s['hands'])}")
    await page.evaluate("__FS.menu()")
    # leaving the app turns the camera off straight away; coming back turns it on again
    await page.evaluate("__FS.start('classic')")
    await wait_state(page, 'playing', timeout=30000)
    await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))""")
    s = await snap(page)
    R.check('[app files] leaving the app pauses and turns the camera off at once', s['state'] == 'paused' and s['camTracks'] == 0 and s['camAsleep'], f"tracks {s['camTracks']}")
    await page.wait_for_timeout(500)
    await page.evaluate("""Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))""")
    await page.wait_for_timeout(4000)
    s = await snap(page)
    R.check('[app files] coming back turns the camera on and finds the hand again', s['camTracks'] == 1 and s['camOn'] and len(s['hands']) == 1 and s['state'] == 'paused', f"tracks {s['camTracks']}, hands {len(s['hands'])}")
    await page.evaluate("__FS.menu(); __FS.check()")
    await page.wait_for_timeout(3000)
    rep = await page.evaluate('__FS.report()')
    R.check('[app files] tracking check works in the app: report says app and local tracker files', f'Version {APP_VERSION} (app)' in rep and 'from local' in rep and 'hand 1: size' in rep, rep[:300])
    await br.close()
    srv.shutdown()

async def realtime_swipe_case(p, R):
    br = await launch(p, video='swipe_sharp')
    ctx, page = await open_game(br, Net(), 1280, 720)
    await start_camera(page)
    xs = []
    t_end = time.time() + 12
    while time.time() < t_end:
        s = await snap(page)
        for h in s['hands']:
            if h['dx'] is not None:
                xs.append(h['dx'])
        await page.wait_for_timeout(100)
    s = await snap(page)
    span = (max(xs) - min(xs)) if xs else 0
    R.check('[live swipe video] cursor follows the moving hand across the screen', span > 500, f"cursor x from {min(xs) if xs else 0:.0f} to {max(xs) if xs else 0:.0f}, tracker {s['detectMs']} ms/frame, page {s['fps']} fps")
    bad = problems(page, allow=MP_NOISE)
    R.check('[live swipe video] console clean', not bad, ' | '.join(bad[:3]))
    await br.close()

# ---------------------------------------------------------------- tracking check screen (Settings > Check hand tracking)
CLIP_JS = """(() => {  // fake clipboard: mode 'ok' = copy works, 'cmd' = only the older copy command, 'none' = all copying blocked
  window.__clip = { mode: 'ok', text: null };
  try {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: (t) => {
      if (window.__clip.mode === 'ok') { window.__clip.text = t; return Promise.resolve(); }
      return Promise.reject(new Error('blocked'));
    } } });
  } catch (e) {}
  const ex = Document.prototype.execCommand;
  Document.prototype.execCommand = function (c, ...a) { if (c === 'copy' && window.__clip.mode === 'none') return false; return ex.call(this, c, ...a); };
})();"""

SEQ_JS = """async ([frUrl, nohandUrl, seq, fps]) => {   // feed a list of [video, frame] (or ['nohand', 0], ['small', scale]) at fps
  window.__imgs2 = window.__imgs2 || {};
  const load = (u) => window.__imgs2[u] || (window.__imgs2[u] = new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = u; }));
  const log = [];
  for (const [name, i] of seq) {
    let img;
    if (name === 'nohand') img = await load(nohandUrl);
    else if (name === 'small') {  // the still hand shrunk to a share of its size: a hand far from the camera
      const im = await load(frUrl + 'swipe_sharp/f001.png'), c = document.createElement('canvas');
      c.width = 640; c.height = 480;
      const g = c.getContext('2d'); g.drawImage(im, 0, 0); g.fillStyle = 'rgb(205,205,205)'; g.fillRect(0, 0, 640, 480);
      g.drawImage(im, 0, 0, 640, 480, 200, 150, 640 * i, 480 * i);
      img = c;
    } else img = await load(frUrl + name + '/f' + String(i + 1).padStart(3, '0') + '.png');
    const tips = await __FS.feed(img, __FS.now());
    log.push(tips ? tips.length : -1);
    __FS.tick(1 / fps, 1);
  }
  __FS.refreshCheck();
  return log;
}"""
FR_URL = pathlib.Path(VIDEOS, 'frames').resolve().as_uri() + '/'
NOHAND_URL = pathlib.Path(VIDEOS, 'nohand_frame0.jpg').resolve().as_uri()

SKEL_JS = """() => {  // skeleton pixels: the light-blue bone colour at the middle of 3 finger bones
  const raw = __FS.raw()[0];
  if (!raw) return null;
  const c = document.getElementById('stage'), k = c.width / c.getBoundingClientRect().width, out = [];
  const copy = document.createElement('canvas'); copy.width = c.width; copy.height = c.height;   // read a copy, not the game canvas
  const g = copy.getContext('2d', { willReadFrequently: true }); g.drawImage(c, 0, 0);
  for (const [a, b] of [[5, 6], [9, 10], [13, 14]]) {
    const A = __FS.toScreen(raw[a].x, raw[a].y), B = __FS.toScreen(raw[b].x, raw[b].y);
    const d = g.getImageData(Math.round((A.x + B.x) / 2 * k) - 2, Math.round((A.y + B.y) / 2 * k) - 2, 5, 5).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200 && d[i + 2] > 200 && d[i + 2] > d[i] + 60) n++;
    out.push(n);
  }
  return out;
}"""
APP_VERSION = json.load(open(os.path.join(ROOT, 'app', 'package.json')))['version']
# true size of the test hand: Python MediaPipe's landmark box in front-back.jpg (make_videos.py), scaled as in the video
HAND_PX = max(530 - 123, 656 - 66) * 260 / 690

NEXT_FRAMES = 'new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))'

async def fresh(page):   # no hands left from the last part, numbers back to zero
    await page.evaluate('__FS.feedOnly(true); __FS.resetDiag()')

async def seq(page, items, fps=30):
    return await page.evaluate(SEQ_JS, [FR_URL, NOHAND_URL, items, fps])

def frames(name, a, b):
    return [[name, i] for i in range(a, b + 1)]

async def reopen_check(page):
    await page.click('#btn-settings'); await page.click('#btn-check')
    return await snap(page)

async def check_case(p, R):
    W, H = 1280, 720
    br = await launch(p, video='static_one')
    ctx, page = await open_game(br, Net(), W, H, init_js=CLIP_JS)
    await page.click('#btn-pointer')
    await page.click('#btn-settings')
    await page.click('#btn-check')
    s = await snap(page)
    R.check('[check] from mouse/touch mode it turns the camera on first (loading screen)', s['state'] == 'loading' and s['ui']['loading'] and not s['ui']['settings'], s['state'])
    await wait_state(page, 'check', timeout=180000)
    await page.wait_for_timeout(6000)
    s = await snap(page)
    N = await page.evaluate('__FS.checkNumbers()')
    vis = await page.evaluate("getComputedStyle(document.getElementById('cam')).opacity")
    R.check('[check] check screen: camera picture, numbers and tip shown; menu and score hidden',
            s['ui']['check'] and s['ui']['checkTip'] and vis == '1' and not s['ui']['hud'] and not s['ui']['menuHead'] and not s['ui']['menuBar'] and s['inputMode'] == 'camera', s['ui']['checkTip'])
    R.check('[check] camera: 640x480, frames arriving, light measured as good', N['video'] == {'w': 640, 'h': 480} and N['camFps'] > 3 and N['luma'] > 80 and not N['dark'],
            f"{N['video']} {N['camFps']:.1f} fps, light {N['luma']}")
    R.check('[check] tracker: results per second, time per frame, same GPU/CPU and thread as the game uses',
            N['resFps'] > 0 and N['tookMs'] > 0 and N['delegate'] == s['delegate'] and N['kind'] == s['trackerKind'] == 'worker' and 0 <= N['skippedPct'] <= 100,
            f"{N['resFps']:.1f}/s, {N['tookMs']:.0f} ms, {N['delegate']}, skipped {N['skippedPct']:.0f}%")
    R.check('[check] delay: camera-to-result is at least the tracker time; capture time known or estimated',
            N['totalMs'] >= N['tookMs'] > 0 and N['capTime'] in ('measured', 'guessed') and N['waitMs'] >= 0, f"total {N['totalMs']:.0f} ms, tracker {N['tookMs']:.0f} ms, capture time {N['capTime']}")
    exp = HAND_PX / 640
    R.check(f'[check] hand size = true hand box ({exp:.1%} of the picture width), tracker sure > 90%',
            len(N['hands']) == 1 and abs(N['hands'][0]['size'] - exp) < 0.02 and N['hands'][0]['sure'] > 0.9, json.dumps(N['hands']))
    rows = s['ui']['checkRows']
    R.check('[check] all 7 rows filled in on screen', all(v and v != '…' for v in rows.values()) and '640×480' in rows['cam'] and 'hand 1: size' in rows['hand'] and 'results/s' in rows['trk'], json.dumps(rows, ensure_ascii=False)[:300])
    px = await page.evaluate(SKEL_JS)
    R.check('[check] hand skeleton drawn on the finger bones', px is not None and all(n >= 2 for n in px), str(px))
    tip0 = s['hands'][0] if s['hands'] else None
    raw8 = (await page.evaluate('__FS.raw()'))[0][8]
    t8 = await page.evaluate(f"__FS.toScreen({raw8['x']}, {raw8['y']})")
    R.check('[check] cursor and skeleton fingertip at the same place (< 8 px)', tip0 and math.hypot(tip0['sx'] - t8['x'], tip0['sy'] - t8['y']) < 8, f"cursor ({tip0 and round(tip0['sx'])},{tip0 and round(tip0['sy'])}) tip ({t8['x']:.0f},{t8['y']:.0f})")
    await page.screenshot(path=f'{OUT}/{TAG}_check_1280x720.png')

    # copy the report
    await page.click('#btn-check-copy')
    await page.wait_for_function('window.__clip.text !== null', timeout=5000)
    text = await page.evaluate('window.__clip.text')
    s = await snap(page)
    need = ('Camera: 640×480', 'Camera can: ', 'Tracker: ', 'Delay (camera to result): ', 'Hands now: hand 1: size ', 'Swipes: ', 'Steadiness', 'Screen: 1280×720', 'Settings: difficulty normal')
    R.check(f'[check] Copy report: report on the clipboard with version {APP_VERSION}, camera, tracker, delay, hand, swipes, screen, settings',
            text.startswith('Fruit Slicer tracking report') and f'Version {APP_VERSION} (website)' in text and all(k in text for k in need), text[:400])
    R.check('[check] says the report was copied', 'copied' in s['ui']['checkNote'] and not s['ui']['checkText'], s['ui']['checkNote'])
    await page.evaluate("window.__clip.mode = 'none'")
    await page.click('#btn-check-copy'); await page.wait_for_timeout(300)
    s = await snap(page)
    shown = await page.evaluate("document.getElementById('check-text').value")
    R.check('[check] copying blocked: the report is shown to copy by hand', s['ui']['checkText'] and 'Could not copy' in s['ui']['checkNote'] and shown.startswith('Fruit Slicer tracking report'), s['ui']['checkNote'])
    await page.evaluate("window.__clip.mode = 'cmd'")
    await page.click('#btn-check-copy'); await page.wait_for_timeout(300)
    s = await snap(page)
    R.check('[check] clipboard refused: the older copy way is tried (copied, or shown to copy by hand)',
            ('copied' in s['ui']['checkNote'] and not s['ui']['checkText']) or ('Could not copy' in s['ui']['checkNote'] and s['ui']['checkText']), s['ui']['checkNote'])
    await page.evaluate("window.__clip.mode = 'ok'")

    # leaving and coming back
    await page.click('#btn-check-done')
    await page.evaluate(NEXT_FRAMES)
    s = await snap(page)
    px = await page.evaluate(SKEL_JS)
    R.check('[check] Done: back to the menu, camera still on, no skeleton', s['state'] == 'menu' and not s['ui']['check'] and not s['ui']['checkTip'] and s['ui']['menuBar'] and s['camOn'] and px is not None and not any(px), str(px))
    s = await reopen_check(page)
    R.check('[check] camera already on: opens at once (no loading)', s['state'] == 'check' and s['ui']['check'] and not s['ui']['loading'])
    r = await page.evaluate('__FS.back()'); s = await snap(page)
    R.check('[check] phone Back button closes it', r is True and s['state'] == 'menu' and not s['ui']['check'])
    await reopen_check(page)
    await page.keyboard.press('Escape'); s = await snap(page)
    R.check('[check] Escape closes it', s['state'] == 'menu' and not s['ui']['check'])
    await reopen_check(page)
    await page.click('#check-x'); s = await snap(page)
    R.check('[check] the X button closes it', s['state'] == 'menu' and not s['ui']['check'])
    await page.evaluate("__FS.setSetting('camView', 'hide')")
    s = await reopen_check(page)
    tint_check = await page.evaluate("getComputedStyle(document.getElementById('tint')).backgroundImage")
    await page.click('#btn-check-done')
    tint_menu = await page.evaluate("getComputedStyle(document.getElementById('tint')).backgroundImage")
    R.check('[check] with "Camera picture: Hide" the check still shows the camera picture (hidden again after)',
            'repeating-linear-gradient' not in tint_check and 'repeating-linear-gradient' in tint_menu, tint_check[:60])
    await page.evaluate("__FS.setSetting('camView', 'show')")

    # frame by frame with the real tracker and a controlled clock (30 fps)
    s = await reopen_check(page)
    await page.evaluate("__FS.feedOnly(true); __FS.setVideoSize(640, 480); __FS.manual(true); __FS.resetDiag()")
    await page.wait_for_timeout(2500)   # a live camera frame may still be in the tracker: let it come back, then clear again
    await fresh(page)
    log = await seq(page, frames('swipe_sharp', 0, 17))
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] still hand: shake measured and small (< 2 px), the cursor shakes less, no jumps, no swipes',
            all(n == 1 for n in log) and N['shakeRaw'] is not None and N['shakeRaw'] < 2 and N['shakeCursor'] <= N['shakeRaw'] and N['jumps'] == 0 and N['swipes'] == 0,
            f"shake {N['shakeRaw']} px raw, {N['shakeCursor']} px cursor, jumps {N['jumps']}, swipes {N['swipes']}, found {log}")
    await fresh(page)
    log = await seq(page, frames('swipe_sharp', 10, 30))
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] one sharp swipe: 1 swipe, hand never lost, gap = one frame (33 ms), nothing broken',
            N['swipes'] == 1 and N['swipeFrames'] >= 8 and N['swipeLost'] == 0 and N['broken'] == 0 and 25 <= N['gapMs'] <= 45,
            f"swipes {N['swipes']}, lost {N['swipeLost']}/{N['swipeFrames']}, gap {N['gapMs']:.0f} ms, broken {N['broken']}, found {log}")
    await fresh(page)
    log = await seq(page, frames('swipe_sharp', 10, 20) + [['nohand', 0]] * 2 + frames('swipe_sharp', 23, 30))
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] hand lost for 2 frames mid-swipe: 2 lost frames, gap 100 ms, swipe not broken',
            N['swipeLost'] == 2 and N['broken'] == 0 and 90 <= N['gapMs'] <= 110 and N['swipes'] == 1,
            f"swipes {N['swipes']}, lost {N['swipeLost']}/{N['swipeFrames']}, gap {N['gapMs']:.0f} ms, broken {N['broken']}, found {log}")
    await fresh(page)
    log = await seq(page, frames('swipe_sharp', 26, 33) + frames('swipe_sharp', 44, 46) + [['nohand', 0]] * 12 + frames('swipe_sharp', 51, 51) * 6)
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] hand lost for 0.4 s mid-swipe: counted as a broken swipe',
            N['broken'] == 1 and N['swipeLost'] >= 5, f"swipes {N['swipes']}, lost {N['swipeLost']}/{N['swipeFrames']}, broken {N['broken']}, found {log}")
    await fresh(page)
    log = await seq(page, frames('swipe_sharp', 0, 9) + [['swipe_sharp', 19]] + frames('swipe_sharp', 10, 17))
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] a one-frame jump of the fingertip is counted (1 jump)', N['jumps'] == 1 and all(n == 1 for n in log), f"jumps {N['jumps']}, found {log}")
    await seq(page, [['nohand', 0]] * 12)
    s = await snap(page)
    R.check('[check] no hand: "Show your hand" tip, no hand in the numbers', 'Show your hand' in s['ui']['checkTip'] and s['ui']['checkRows']['hand'] == 'no hand found', s['ui']['checkTip'])
    log = await seq(page, [['small', 0.3]] * 4)
    s = await snap(page)
    N = await page.evaluate('__FS.checkNumbers()')
    R.check('[check] hand far away (small in the picture): "Come closer" tip', all(n == 1 for n in log) and 'Come closer' in s['ui']['checkTip'] and N['hands'] and N['hands'][0]['size'] < 0.12,
            f"{s['ui']['checkTip']} {json.dumps(N['hands'])} found {log}")
    log = await seq(page, frames('swipe_sharp', 0, 17))   # 0.6 s: the small hand's trail (0.3 s) is gone
    s = await snap(page)
    R.check('[check] hand close again: back to the normal tip', 'Swipe your hand' in s['ui']['checkTip'], s['ui']['checkTip'])
    errs = await page.evaluate('window.__FS_ERRORS || []')
    R.check('[check] no frame errors', not errs, str(errs[:2]))
    bad = problems(page, MP_NOISE)
    R.check('[check] console clean', not bad, ' | '.join(bad[:3]))
    await br.close()

async def check_layout_case(p, R):
    br = await launch(p, video='portrait_one')
    ctx, page = await open_game(br, Net(), 412, 915, mobile=True, dpr=2)
    await start_camera(page)
    await page.evaluate('__FS.check()')
    await wait_state(page, 'check', timeout=30000)
    await page.wait_for_timeout(4000)
    for (w, h) in ((412, 915), (915, 412), (360, 740)):
        await page.set_viewport_size({'width': w, 'height': h})
        await page.wait_for_timeout(700)
        await page.evaluate('__FS.refreshCheck()')
        box = await page.locator('#check').bounding_box()
        tip = await page.locator('#check-tip').bounding_box()
        btns = [await page.locator(sel).bounding_box() for sel in ('#btn-check-copy', '#btn-check-reset', '#btn-check-done')]
        scroll_w = await page.evaluate('document.documentElement.scrollWidth')
        inside = box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= w + 0.5 and box['y'] + box['height'] <= h + 0.5 and scroll_w <= w
        if h > w:   # upright phone: the numbers stay in the lower part, the hand has the top
            room = box['y'] >= 0.45 * h
        else:       # sideways: numbers on the left half, tip on the right half
            room = box['x'] + box['width'] <= 0.52 * w and tip['x'] >= box['x'] + box['width']
        no_overlap = tip['y'] + tip['height'] <= box['y'] or tip['x'] >= box['x'] + box['width']
        btn_ok = all(b and b['height'] >= 36 and b['y'] + b['height'] <= h for b in btns)
        R.check(f'[check layout {w}x{h}] numbers fully on screen, room left for the hand, tip clear of the numbers, buttons usable',
                inside and room and no_overlap and btn_ok, f"card {box}, tip {tip}, page width {scroll_w}")
        await page.screenshot(path=f'{OUT}/{TAG}_check_{w}x{h}.png')
    bad = problems(page, MP_NOISE)
    R.check('[check layout] console clean', not bad, ' | '.join(bad[:3]))
    await br.close()

async def main():
    R = Report(f'Suite B v2 camera ({TAG})')
    async with async_playwright() as p:
        cases = {
            'static': lambda: mapping_case(p, R, 'static_one', 1280, 720, False),
            'two': lambda: mapping_case(p, R, 'two_static', 1280, 720, False),
            'portrait': lambda: mapping_case(p, R, 'portrait_one', 412, 915, True),
            'nohand': lambda: nohand_case(p, R),
            'dark': lambda: dark_case(p, R),
            'asl': lambda: asl_case(p, R),
            'feed_sharp': lambda: feed_case(p, R, 'swipe_sharp'),
            'feed_blur': lambda: feed_case(p, R, 'swipe_blur'),
            'feed_slow': lambda: feed_slow_case(p, R, 'swipe_sharp'),
            'gpu': lambda: gpu_switch_case(p, R),
            'noworker': lambda: noworker_case(p, R),
            'nofileflag': lambda: nofileflag_case(p, R),
            'app': lambda: app_case(p, R),
            'live': lambda: realtime_swipe_case(p, R),
            'check': lambda: check_case(p, R),
            'checklayout': lambda: check_layout_case(p, R),
        }
        for name, fn in cases.items():
            if ONLY and name not in ONLY:
                continue
            try:
                await fn()
            except Exception as e:
                R.check(f'[{name}] ran without crashing', False, repr(e)[:300])
    sys.exit(1 if R.summary() else 0)

asyncio.run(main())
