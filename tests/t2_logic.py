"""Suite A (v2): rules, modes, power-ups, settings, progress and stability with a controlled clock (no camera)."""
import asyncio, json, math, sys
from playwright.async_api import async_playwright
from harness import *

TAG = sys.argv[1] if len(sys.argv) > 1 else 'r1'
ONLY = sys.argv[2] if len(sys.argv) > 2 else None   # 'desktop' or 'phone'
HELPERS = """
window.__sw = 0;
// a straight stroke: steps+1 points spread over dur seconds, starting at t0 (default: now)
window.__swipe = (x0, y0, x1, y1, dur, steps, o) => {
  o = o || {};
  const id = o.id || ('test' + (++window.__sw)), t0 = o.t0 == null ? __FS.now() : o.t0;
  for (let i = 0; i <= steps; i++) { const f = i / steps; __FS.point(id, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, t0 + dur * f, o.primary !== false); }
  if (!o.keep) __FS.end(id);
  return id;
};
"""

async def ev(page, js, arg=None):
    return await page.evaluate(js, arg) if arg is not None else await page.evaluate(js)

async def tick(page, seconds, dt=1/60):
    steps = max(1, round(seconds / dt))
    await page.evaluate(f'__FS.tick({dt}, {steps})')

async def to_playing(page, mode='classic'):
    await ev(page, f"__FS.start('{mode}')")
    await tick(page, 1.95)
    s = await snap(page)
    assert s['state'] == 'playing', s['state']
    return s

async def swipe_through(page, x, y, half=200, dur=0.1, steps=8, **o):
    await ev(page, f"__swipe({x - half}, {y}, {x + half}, {y}, {dur}, {steps}, {json.dumps(o)})")

async def click_or_tap(page, mobile, x, y):
    if mobile:
        await page.touchscreen.tap(x, y)
    else:
        await page.mouse.click(x, y)


async def suite(width, height, mobile, R):
    dev = f'{width}x{height}'
    async with async_playwright() as p:
        br = await launch(p)
        net = Net()
        # an old version-1 player: best score 42 and sound muted must carry over
        init = "try { if (!sessionStorage.getItem('seeded')) { localStorage.clear(); localStorage.setItem('fruitSlicer.best.classic', '42'); localStorage.setItem('fruitSlicer.muted', '1'); sessionStorage.setItem('seeded', '1'); } } catch (e) {}"
        ctx, page = await open_game(br, net, width, height, mobile=mobile, dpr=2 if mobile else 1, init_js=init)
        await ev(page, HELPERS)
        await page.wait_for_timeout(600)
        s = await snap(page)
        R.check(f'[{dev}] intro shown, HUD hidden at start', s['ui']['intro'] and not s['ui']['hud'] and s['state'] == 'intro')
        outside = [u for u in net.log if not u.startswith('file://') and not u.startswith('data:')]
        R.check(f'[{dev}] page loads with no internet requests (fonts are built in)', not outside, str(outside[:3]))
        fonts_ok = await page.evaluate("(() => { let n = 0, ok = 0; document.fonts.forEach(f => { n++; if (f.status === 'loaded') ok++; }); return n === 5 && ok === 5; })()")
        R.check(f'[{dev}] built-in fonts load', fonts_ok)
        cam = await page.evaluate("({ poster: document.getElementById('cam').poster.slice(0, 14), opacity: getComputedStyle(document.getElementById('cam')).opacity })")
        R.check(f'[{dev}] camera layer invisible before the camera starts (no grey video placeholder on phones)', cam['poster'] == 'data:image/gif' and cam['opacity'] == '0', json.dumps(cam))
        R.check(f'[{dev}] version-1 best score and mute setting carried over', s['best']['classic'] == 42 and s['settings']['muted'] is True, f"best {s['best']}, muted {s['settings']['muted']}")
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_intro.png')

        # ---------------------------------------------------------------- menu
        await page.click('#btn-pointer')
        s = await snap(page)
        R.check(f'[{dev}] menu: Classic, Arcade, Zen fruit + Settings and Progress buttons',
                s['state'] == 'menu' and [t['id'] for t in s['targets']] == ['classic', 'arcade', 'zen'] and s['ui']['menuBar'] and s['ui']['menuHead'] and not s['ui']['intro'])
        await ev(page, '__FS.manual(true)'); await ev(page, '__FS.seed(12345)')
        await tick(page, 0.5)
        s = await snap(page)
        tg = {t['id']: t for t in s['targets']}
        title_box = await page.locator('#menu-head .title').bounding_box()
        bar_box = await page.locator('#menu-bar .btn').first.bounding_box()
        bad = []
        for t in s['targets']:
            ring = t['r'] * 1.28
            if t['x'] - ring < 0 or t['x'] + ring > width: bad.append(t['id'] + ' off side')
            if t['y'] - ring < title_box['y'] + title_box['height']: bad.append(t['id'] + ' under title')
            if t['y'] + ring + 34 > bar_box['y']: bad.append(t['id'] + ' over buttons')
        ts = s['targets']
        for i in range(3):
            for j in range(i + 1, 3):
                if math.hypot(ts[i]['x'] - ts[j]['x'], ts[i]['y'] - ts[j]['y']) < 2 * ts[i]['r'] * 1.28 + 30: bad.append(f'{ts[i]["id"]}-{ts[j]["id"]} overlap')
        R.check(f'[{dev}] menu fruit fully on screen, between title and buttons, not overlapping', not bad, '; '.join(bad) + ' ' + json.dumps([(round(t['x']), round(t['y']), round(t['r'])) for t in ts]))
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_menu.png')

        # ---------------------------------------------------------------- settings panel (default values, blocking cuts)
        await page.click('#btn-settings')
        s = await snap(page)
        R.check(f'[{dev}] Settings opens with saved values', s['ui']['settings'] and await page.is_checked('#diff-normal') and await page.is_checked('#sens-normal') and await page.is_checked('#cut-hand') and await page.is_checked('#cam-show'))
        a = tg['arcade']
        await swipe_through(page, a['x'], a['y'], half=a['r'] * 2)
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] swipes do nothing while Settings is open', s['state'] == 'menu' and not any(t['sliced'] for t in s['targets']))
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_settings.png', full_page=False)
        await page.keyboard.press('Escape')
        s = await snap(page)
        R.check(f'[{dev}] Escape closes Settings', not s['ui']['settings'] and s['state'] == 'menu')

        # ---------------------------------------------------------------- tracking check button (opening it with no camera: t2_errors.py)
        await page.click('#btn-settings')
        s = await snap(page)
        R.check(f'[{dev}] Settings from the menu has "Check hand tracking"', s['ui']['checkRow'] and await page.is_visible('#btn-check'))
        await page.click('#settings-done')

        # ---------------------------------------------------------------- tap Classic
        c = tg['classic']
        await click_or_tap(page, mobile, c['x'], c['y'])
        s = await snap(page)
        R.check(f'[{dev}] tapping Classic fruit slices it', s['pending'] == 'classic' and any(t['sliced'] for t in s['targets'] if t['id'] == 'classic'))
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] Classic countdown: misses shown, no timer, no power-ups bar, menu buttons hidden',
                s['state'] == 'countdown' and s['mode'] == 'classic' and s['ui']['pauseBtn'] and s['ui']['livesShown'] and not s['ui']['timerShown'] and not s['ui']['powersShown'] and not s['ui']['menuBar'])
        await tick(page, 1.9)
        s = await snap(page)
        R.check(f'[{dev}] playing after 3-2-1', s['state'] == 'playing' and s['score'] == 0 and s['lives'] == 3)
        R.check(f'[{dev}] first achievement not yet unlocked', 'first' not in s['ach'])

        # ---------------------------------------------------------------- slicing rules (Normal sensitivity)
        await ev(page, '__FS.spawning(false)')
        W, H, MIN = s['W'], s['H'], s['MIN']
        cx, cy = W / 2, H * 0.55
        thr = 0.6 * MIN
        await ev(page, f"__FS.spawn({{type:'orange', x:{cx}, y:{cy}, frozen:true}})")
        r = (await snap(page))['items'][0]['r']
        dist = 300
        await ev(page, f'__swipe({cx - 150}, {cy}, {cx + 150}, {cy}, {dist / (thr * 0.5)}, 40)')
        await tick(page, dist / (thr * 0.5) + 0.1)
        s = await snap(page)
        R.check(f'[{dev}] slow movement through a fruit does not cut', len(s['items']) == 1 and s['score'] == 0, f'speed {thr * 0.5:.0f}px/s < {thr:.0f}')
        off = r * 1.3 + 8
        await swipe_through(page, cx, cy + off, dur=0.12)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] fast swipe passing outside the fruit does not cut', len(s['items']) == 1 and s['score'] == 0, f'offset {off:.0f}px, r {r:.0f}')
        off = r * 1.3 - 6
        await swipe_through(page, cx, cy + off, dur=0.12)
        await tick(page, 0.3)
        s = await snap(page)
        R.check(f'[{dev}] fast swipe at the fruit edge cuts it', len(s['items']) == 0 and s['score'] == 1 and s['halves'] == 2, f'offset {off:.0f}px')
        R.check(f'[{dev}] first slice unlocks "First Slice" + Mango blade with a message', 'first' in s['ach'] and s['ui']['toast'] and 'First Slice' in s['ui']['toastTitle'], s['ui']['toastTitle'])
        await ev(page, f"__FS.spawn({{type:'apple', x:{cx}, y:{cy}, frozen:true}})")
        await ev(page, f"(() => {{ const t = __FS.now(); __FS.point('tp', 10, {cy}, t); __FS.point('tp', {W - 10}, {cy}, t + 0.033); __FS.end('tp'); }})()")
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] a sudden jump across the screen does not cut', len(s['items']) == 1 and s['score'] == 1)
        await ev(page, f"(() => {{ const t = __FS.now(); __FS.point('gap', {cx - 150}, {cy}, t); __FS.point('gap', {cx + 150}, {cy}, t + 0.3); __FS.end('gap'); }})()")
        await tick(page, 0.4)
        s = await snap(page)
        R.check(f'[{dev}] mouse/touch: a long pause then a new point does not cut', len(s['items']) == 1 and s['score'] == 1)
        await ev(page, f"(() => {{ const t = __FS.now(); __FS.point('flick', {cx - 120}, {cy - 20}, t); __FS.point('flick', {cx + 120}, {cy + 20}, t + 0.066); __FS.end('flick'); }})()")
        await tick(page, 0.3)
        s = await snap(page)
        R.check(f'[{dev}] fast flick at 15 fps (2 samples) cuts', len(s['items']) == 0 and s['score'] == 2)
        await ev(page, f"__FS.spawn({{type:'apple', x:{cx}, y:{cy}, frozen:true}})")
        step = MIN * 0.45
        await ev(page, f"(() => {{ const t = __FS.now(); __FS.point('slow10', {cx - step}, {cy}, t); __FS.point('slow10', {cx}, {cy + 5}, t + 0.1); __FS.point('slow10', {cx + step}, {cy + 10}, t + 0.2); __FS.end('slow10'); }})()")
        await tick(page, 0.3)
        s = await snap(page)
        R.check(f'[{dev}] swipe seen by a slow 10 fps tracker still cuts', len(s['items']) == 0 and s['score'] == 3, f"score {s['score']}")
        # camera hand lost for 0.28 s mid-swipe, found again past the fruit: still cuts (it passed through)
        await ev(page, f"__FS.spawn({{type:'kiwi', x:{cx}, y:{cy}, frozen:true}})")
        await ev(page, f"(() => {{ const t = __FS.now(); __FS.point('c700t', {cx - 260}, {cy}, t); __FS.point('c700t', {cx - 200}, {cy}, t + 0.033); __FS.point('c700t', {cx + 200}, {cy}, t + 0.31); __FS.end('c700t'); }})()")
        await tick(page, 0.3)
        s = await snap(page)
        R.check(f'[{dev}] camera: hand lost for a moment mid-swipe still cuts the fruit it passed', len(s['items']) == 0 and s['score'] == 4, f"score {s['score']}")

        # ---------------------------------------------------------------- lag compensation
        await ev(page, f"__FS.spawn({{type:'watermelon', x:{cx}, y:{H * 0.95}, vx:0, vy:{-H * 1.4}}})")
        await tick(page, 0.25)
        cur = (await snap(page))['items'][0]
        fid = cur['id']
        now = await ev(page, '__FS.now()')
        past = await ev(page, f'__FS.posAt({fid}, {now - 0.15})')
        R.check(f'[{dev}] fruit position history works (fruit moved {abs(cur["y"] - past["y"]):.0f}px in 0.15 s)', abs(cur['y'] - past['y']) > 1.3 * cur['r'] + 20, f"r {cur['r']}")
        # stroke from frames taken 0.15 s ago, through where the fruit was then (not where it is drawn now)
        await swipe_through(page, cx, past['y'], dur=0.02, steps=2, t0=now - 0.16, id='lagA')
        s = await snap(page)
        R.check(f'[{dev}] late camera frames: swipe through where the fruit WAS at that moment cuts it', s['score'] == 5 and not any(i['id'] == fid for i in s['items']), f"score {s['score']}")
        await tick(page, 0.6)
        # bomb: a late stroke through where the bomb is drawn now (it was elsewhere when the frames were taken) does not explode
        await ev(page, f"__FS.spawn({{kind:'bomb', x:{cx}, y:{H * 0.95}, vx:0, vy:{-H * 1.4}}})")
        await tick(page, 0.25)
        b = (await snap(page))['items'][0]
        now = await ev(page, '__FS.now()')
        bpast = await ev(page, f"__FS.posAt({b['id']}, {now - 0.15})")
        await swipe_through(page, cx, b['y'], dur=0.02, steps=2, t0=now - 0.16, id='c801t')
        s = await snap(page)
        R.check(f'[{dev}] late camera frames: bomb NOT set off by a swipe through where it is only drawn now', s['lives'] == 3 and len(s['items']) == 1, f"lives {s['lives']}")
        await swipe_through(page, cx, bpast['y'], dur=0.02, steps=2, t0=now - 0.16, id='c802t')
        s = await snap(page)
        R.check(f'[{dev}] late camera frames: bomb set off by a swipe through where it really was', s['lives'] == 2 and len(s['items']) == 0, f"lives {s['lives']}")
        await tick(page, 1.0)

        # ---------------------------------------------------------------- whole hand: knuckles/wrist cut fruit, never bombs
        await ev(page, f"__FS.spawn({{kind:'bomb', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy, primary=False)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] knuckle/wrist passing through a bomb does not set it off', s['lives'] == 2 and len(s['items']) == 1)
        await ev(page, '__FS.start("classic")'); await tick(page, 1.95); await ev(page, '__FS.spawning(false)')
        await ev(page, f"__FS.spawn({{type:'lemon', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy, primary=False)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] knuckle/wrist passing through a fruit cuts it', s['score'] == 1 and len(s['items']) == 0)

        # ---------------------------------------------------------------- combos
        for k, typ in enumerate(['kiwi', 'lemon', 'mango']):
            await ev(page, f"__FS.spawn({{type:'{typ}', x:{cx - MIN * 0.3 + k * MIN * 0.3}, y:{cy}, frozen:true}})")
        await ev(page, f'__swipe({cx - MIN * 0.5}, {cy}, {cx + MIN * 0.5}, {cy}, 0.12, 12)')
        await tick(page, 0.4)
        s = await snap(page)
        R.check(f'[{dev}] 3-fruit combo gives +3 bonus', s['score'] == 1 + 3 + 3 and any('Combo x3' in t for t in s['texts']), f"score {s['score']} texts {s['texts']}")
        R.check(f'[{dev}] combo of 3 unlocks "Combo!"', 'combo3' in s['ach'])
        for k in range(2):
            await ev(page, f"__FS.spawn({{type:'apple', x:{cx - MIN * 0.15 + k * MIN * 0.3}, y:{cy}, frozen:true}})")
        await ev(page, f'__swipe({cx - MIN * 0.4}, {cy}, {cx + MIN * 0.4}, {cy}, 0.1, 10)')
        await tick(page, 0.4)
        s = await snap(page)
        R.check(f'[{dev}] 2 fruits in one swipe: no bonus', s['score'] == 9, f"score {s['score']}")
        # one hand: fingertip cuts 1 fruit, knuckle cuts 2 more in the same swipe -> one combo of 3
        ys = [cy - MIN * 0.25, cy, cy + MIN * 0.12]
        for k in range(3):
            await ev(page, f"__FS.spawn({{type:'orange', x:{cx}, y:{ys[k]}, frozen:true}})")
        await ev(page, f"""(() => {{ const t = __FS.now();
            __swipe({cx - 220}, {ys[0]}, {cx + 220}, {ys[0]}, 0.06, 6, {{id: 'c60t', t0: t, keep: true}});
            __swipe({cx - 220}, {ys[1]}, {cx + 220}, {ys[1]}, 0.06, 6, {{id: 'c60k', t0: t + 0.01, keep: true, primary: false}});
            __swipe({cx - 220}, {ys[2]}, {cx + 220}, {ys[2]}, 0.06, 6, {{id: 'c60w', t0: t + 0.02, keep: true, primary: false}});
            __FS.end('c60t'); __FS.end('c60k'); __FS.end('c60w'); }})()""")
        await tick(page, 0.4)
        s = await snap(page)
        R.check(f'[{dev}] fingertip + knuckle + wrist of one hand make one combo', s['score'] == 9 + 3 + 3, f"score {s['score']} texts {s['texts']}")

        # ---------------------------------------------------------------- bombs, misses, game over (Classic)
        await ev(page, f"__FS.spawn({{kind:'bomb', x:{cx}, y:{cy}, frozen:true}})")
        br_ = (await snap(page))['items'][0]['r']
        await swipe_through(page, cx, cy + br_ * 0.95)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] grazing a bomb (outside 0.9 r) is forgiven', len(s['items']) == 1 and s['lives'] == 3)
        await swipe_through(page, cx, cy)
        await tick(page, 0.1)
        s = await snap(page)
        R.check(f'[{dev}] slicing a bomb costs 1 life in Classic', len(s['items']) == 0 and s['lives'] == 2 and s['ui']['livesLost'] == 1 and s['score'] == 15 and 'Boom!' in s['texts'], f"lives {s['lives']} score {s['score']}")
        await ev(page, f"__FS.spawn({{type:'lemon', x:{cx}, y:{H - 10}, vx:0, vy:{H * 0.5}}})")
        await tick(page, 1.0)
        s = await snap(page)
        R.check(f'[{dev}] a fruit falling off the bottom costs 1 life', s['lives'] == 1 and s['marks'] >= 1)
        await ev(page, f"__FS.spawn({{kind:'bomb', x:{cx}, y:{H - 10}, vx:0, vy:{H * 0.5}}})")
        await tick(page, 1.0)
        s = await snap(page)
        R.check(f'[{dev}] a bomb falling away costs nothing', s['lives'] == 1 and len(s['items']) == 0)
        await ev(page, f"__FS.spawn({{type:'kiwi', x:{cx}, y:{H - 10}, vx:0, vy:{H * 0.5}}})")
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] 3rd miss ends the game', s['state'] == 'over' and s['lives'] == 0 and not s['ui']['pauseBtn'])
        await tick(page, 1.1)
        s = await snap(page)
        R.check(f'[{dev}] results: score, best (old best 42 kept), extra line', s['resultsShown'] and s['ui']['resTitle'] == 'Game over' and s['ui']['resScore'] == '15'
                and not s['ui']['resNew'] and s['best']['classic'] == 42 and 'Fruit sliced 9' in s['ui']['resExtra'] and 'Best combo 3' in s['ui']['resExtra'], s['ui']['resExtra'])
        R.check(f'[{dev}] results: Play again + Menu fruit', [t['id'] for t in s['targets']] == ['again', 'menu'])
        await tick(page, 0.7)
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_results.png')
        s = await snap(page)
        card = await page.locator('#results .result-card').bounding_box()
        top_ring = min(t['y'] - t['r'] * 1.28 for t in s['targets'])
        R.check(f'[{dev}] results card does not cover the fruit', card['y'] + card['height'] < top_ring, f"card bottom {card['y'] + card['height']:.0f}, fruit ring top {top_ring:.0f}")
        ag = [t for t in s['targets'] if t['id'] == 'again'][0]
        await swipe_through(page, ag['x'], ag['y'], half=250, dur=0.12, steps=10)
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] swiping "Play again" restarts Classic fresh', s['state'] == 'countdown' and s['score'] == 0 and s['lives'] == 3 and s['ui']['livesLost'] == 0 and s['ui']['scoreText'] == '0')
        await tick(page, 1.9)

        # ---------------------------------------------------------------- pause / settings from pause / back button
        await ev(page, f"__FS.spawn({{type:'apple', x:{cx}, y:{cy}, vx:0, vy:-100}})")
        await page.keyboard.press('Space')
        s1 = await snap(page)
        await tick(page, 1.0)
        s2 = await snap(page)
        R.check(f'[{dev}] Space pauses; game frozen while paused', s1['state'] == 'paused' and s1['ui']['pause'] and s1['items'] == s2['items'])
        await page.click('#btn-pause-settings')
        s = await snap(page)
        R.check(f'[{dev}] Settings opens from the pause screen', s['ui']['settings'] and not s['ui']['pause'] and s['state'] == 'paused')
        R.check(f'[{dev}] no "Check hand tracking" in the middle of a paused game', not s['ui']['checkRow'] and not await page.is_visible('#btn-check'))
        await page.click('#settings-done')
        s = await snap(page)
        R.check(f'[{dev}] closing Settings returns to the pause screen', not s['ui']['settings'] and s['ui']['pause'] and s['state'] == 'paused')
        await page.keyboard.press('Space')
        s = await snap(page)
        R.check(f'[{dev}] Space resumes', s['state'] == 'playing' and not s['ui']['pause'])
        r1 = await ev(page, '__FS.back()'); s = await snap(page)
        R.check(f'[{dev}] phone Back button during play pauses (and is handled)', r1 is True and s['state'] == 'paused')
        r2 = await ev(page, '__FS.back()'); s = await snap(page)
        R.check(f'[{dev}] Back on the pause screen goes to the menu', r2 is True and s['state'] == 'menu')
        r3 = await ev(page, '__FS.back()')
        R.check(f'[{dev}] Back in the menu lets the app close', r3 is False)
        await page.click('#btn-settings')
        r4 = await ev(page, '__FS.back()'); s = await snap(page)
        R.check(f'[{dev}] Back closes Settings first', r4 is True and not s['ui']['settings'] and s['state'] == 'menu')
        await page.click('#btn-settings')
        s = await snap(page)
        R.check(f'[{dev}] "Check hand tracking" is back when Settings opens from the menu', s['ui']['checkRow'])
        await page.click('#settings-done')
        await to_playing(page, 'classic')
        await page.click('#btn-pause'); await page.click('#btn-restart')
        s = await snap(page)
        R.check(f'[{dev}] Restart from pause starts a new countdown', s['state'] == 'countdown' and s['score'] == 0 and len(s['items']) == 0 and not s['ui']['pause'])
        await tick(page, 1.9)
        await page.click('#btn-pause'); await page.click('#btn-menu')
        s = await snap(page)
        R.check(f'[{dev}] Menu from pause goes to the menu', s['state'] == 'menu' and s['ui']['menuHead'] and not s['ui']['pause'])

        # ---------------------------------------------------------------- Arcade + power-ups
        s = await to_playing(page, 'arcade')
        R.check(f'[{dev}] Arcade: 60 s timer, no misses, power-up bar', s['ui']['timerShown'] and s['ui']['timerText'] == '60' and not s['ui']['livesShown'] and s['ui']['powersShown'])
        await ev(page, '__FS.spawning(false)')
        # Freeze
        await ev(page, f"__FS.spawn({{kind:'power', type:'freeze', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy)
        s = await snap(page)
        R.check(f'[{dev}] slicing the blue banana starts Freeze', s['powers']['freeze'] > 4.9 and s['timeScale'] == 0.4 and s['ui']['frost'] and s['ui']['pchips'] == ['freeze'] and s['score'] == 1, json.dumps(s['powers']))
        t_before = s['timeLeft']
        await ev(page, f"__FS.spawn({{type:'apple', x:{cx}, y:{cy}, vx:300, vy:0}})")
        x0 = (await snap(page))['items'][0]['x']
        await tick(page, 0.5)
        s = await snap(page)
        dx = s['items'][0]['x'] - x0
        R.check(f'[{dev}] Freeze: fruit move at 40% speed and the clock stops', abs(dx - 300 * 0.5 * 0.4) < 3 and s['timeLeft'] == t_before, f"moved {dx:.1f}px (expected 60), timer {t_before} -> {s['timeLeft']}")
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_freeze.png')
        await tick(page, 4.7)
        s = await snap(page)
        R.check(f'[{dev}] Freeze ends after 5 s', s['powers']['freeze'] == 0 and s['timeScale'] == 1 and not s['ui']['frost'] and s['ui']['pchips'] == [] and s['timeLeft'] < t_before, json.dumps(s['powers']))
        await ev(page, "__FS.spawning(false)")
        await tick(page, 3)
        # Double
        score0 = (await snap(page))['score']
        await ev(page, f"__FS.spawn({{kind:'power', type:'double', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy)
        await tick(page, 0.4)
        for k in range(3):
            await ev(page, f"__FS.spawn({{type:'kiwi', x:{cx - MIN * 0.3 + k * MIN * 0.3}, y:{cy}, frozen:true}})")
        await ev(page, f'__swipe({cx - MIN * 0.5}, {cy}, {cx + MIN * 0.5}, {cy}, 0.12, 12)')
        await tick(page, 0.4)
        s = await snap(page)
        R.check(f'[{dev}] Double: 3 fruit = 6 points + combo bonus 6', s['score'] - score0 == 1 + 6 + 6 and any('Combo x3' in t and '+6' in t for t in s['texts']), f"gained {s['score'] - score0}, texts {s['texts']}")
        await tick(page, 7)
        s = await snap(page)
        R.check(f'[{dev}] Double ends after 7 s', s['powers']['double'] == 0)
        # Frenzy
        side0 = (await snap(page))['stats']['sideSpawned']; bombs0 = (await snap(page))['stats']['bombSpawned']
        await ev(page, "__FS.spawning(true)")
        await ev(page, f"__FS.spawn({{kind:'power', type:'frenzy', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy)
        s = await snap(page)
        R.check(f'[{dev}] slicing the orange banana starts Frenzy', s['powers']['frenzy'] > 3.9)
        await tick(page, 2.0)
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_frenzy.png')
        await tick(page, 2.1)
        s = await snap(page)
        n_side = s['stats']['sideSpawned'] - side0
        R.check(f'[{dev}] Frenzy throws a stream of fruit from both sides for 4 s', 20 <= n_side <= 34 and s['powers']['frenzy'] == 0, f'{n_side} side fruit')
        R.check(f'[{dev}] all 3 power-ups in one game unlocks "Power Player" (Ice blade)', 'power3' in s['ach'])
        await ev(page, "__FS.spawning(false)")
        await tick(page, 2)
        await ev(page, "__FS.clearItems()")
        await ev(page, f"__FS.spawn({{kind:'bomb', x:{cx}, y:{cy}, frozen:true}})")
        sc = (await snap(page))['score']
        await swipe_through(page, cx, cy)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] Arcade: a bomb takes 10 points, no life lost', s['score'] == max(0, sc - 10) and s['state'] == 'playing', f"{sc} -> {s['score']}")
        await ev(page, "__FS.power('double')")
        t_left = s['timeLeft']
        await tick(page, t_left - 0.5, dt=1 / 30)
        s = await snap(page)
        R.check(f'[{dev}] Arcade timer counts down (0.5 s left shows 1)', s['state'] == 'playing' and s['ui']['timerText'] == '1', s['ui']['timerText'])
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] Arcade ends at 0 with power-ups cleared', s['state'] == 'over' and s['ui']['timerText'] == '0' and all(v == 0 for v in s['powers'].values()) and not s['ui']['frost'])
        await tick(page, 1.2)
        s = await snap(page)
        R.check(f"[{dev}] Arcade results say \"Time's up!\" and record the best", s['ui']['resTitle'] == "Time's up!" and s['ui']['results'] and s['best']['arcade'] == s['score'] and s['ui']['resNew'], f"best {s['best']}")
        mn = [t for t in s['targets'] if t['id'] == 'menu'][0]
        await tick(page, 0.7)
        await click_or_tap(page, mobile, mn['x'], mn['y'])
        await tick(page, 0.6)
        s = await snap(page)
        R.check(f'[{dev}] tapping "Menu" fruit returns to menu, Arcade best shown', s['state'] == 'menu')

        # natural Arcade game: power-ups appear, one at a time
        await ev(page, '__FS.seed(31337)'); await ev(page, '__FS.spawning(true)')
        await to_playing(page, 'arcade')
        pw0 = (await snap(page))['stats']['powerSpawned']
        most = 0
        for _ in range(61):
            most = max(most, await page.evaluate("""() => { let most = 0; for (let i = 0; i < 30; i++) { __FS.tick(1 / 30, 1); const n = __FS.snap().items.filter(i => i.kind === 'power').length; if (n > most) most = n; } return most; }"""))
        s = await snap(page)
        R.check(f'[{dev}] natural Arcade game: power-ups appear, never 2 at once', s['stats']['powerSpawned'] - pw0 >= 2 and most == 1, f"{s['stats']['powerSpawned'] - pw0} spawned, max on screen {most}")
        R.check(f'[{dev}] natural Arcade game ends by time', s['state'] == 'over')

        # ---------------------------------------------------------------- Zen
        s = await to_playing(page, 'zen')
        R.check(f'[{dev}] Zen: 90 s timer, no misses, no power-up bar', s['ui']['timerShown'] and s['ui']['timerText'] == '90' and not s['ui']['livesShown'] and not s['ui']['powersShown'])
        b0 = s['stats']['bombSpawned']; p0 = s['stats']['powerSpawned']; m0 = s['stats']['missed']
        await tick(page, 89.0, dt=1 / 30)
        s = await snap(page)
        R.check(f'[{dev}] Zen: 89 s of fruit, no bombs, no power-ups, misses cost nothing', s['state'] == 'playing' and s['stats']['bombSpawned'] == b0 and s['stats']['powerSpawned'] == p0 and s['stats']['missed'] > m0,
                f"bombs {s['stats']['bombSpawned'] - b0}, missed {s['stats']['missed'] - m0}")
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_zen.png')
        await tick(page, 1.5)
        s = await snap(page)
        R.check(f"[{dev}] Zen ends with \"Time's up!\"", s['state'] == 'over' and s['ui']['resTitle'] == "Time's up!")

        # natural Classic game: no power-ups
        await ev(page, '__FS.seed(777)')
        await to_playing(page, 'classic')
        p0 = (await snap(page))['stats']['powerSpawned']
        await tick(page, 40, dt=1 / 30)
        s = await snap(page)
        R.check(f'[{dev}] Classic with no input: ends by misses, no power-ups', s['state'] == 'over' and s['stats']['powerSpawned'] == p0)

        # ---------------------------------------------------------------- settings change the game
        await ev(page, '__FS.menu()')
        await page.click('#btn-settings')
        await page.click('label:has(#sens-easy)')
        await page.click('label:has(#diff-hard)')
        await page.click('label:has(#cam-hide)')
        await page.evaluate("(() => { const r = document.getElementById('set-music'); r.value = '20'; r.dispatchEvent(new Event('input', {bubbles: true})); })()")
        s = await snap(page)
        saved = json.loads(await page.evaluate("localStorage.getItem('fruitSlicer.settings')"))
        R.check(f'[{dev}] Settings: choices apply at once and are saved', s['settings']['sens'] == 'easy' and s['settings']['diff'] == 'hard' and s['settings']['camView'] == 'hide' and s['settings']['music'] == 20
                and saved['sens'] == 'easy' and saved['music'] == 20 and s['ui']['camHidden'] and (await page.text_content('#out-music')) == '20', json.dumps(saved))
        await page.click('#settings-done')
        s = await to_playing(page, 'classic')
        R.check(f'[{dev}] Hard difficulty: stronger gravity (faster fruit) in the next game', abs(s['G'] - 1.25 * s['H'] * 1.12) < 0.5, f"G {s['G']:.1f}")
        await ev(page, '__FS.spawning(false)')
        await ev(page, f"__FS.spawn({{type:'orange', x:{cx}, y:{cy}, frozen:true}})")
        await ev(page, f'__swipe({cx - 150}, {cy}, {cx + 150}, {cy}, {300 / (0.5 * MIN)}, 30)')
        await tick(page, 300 / (0.5 * MIN) + 0.1)
        s = await snap(page)
        R.check(f'[{dev}] Easy cutting: a calm swipe (0.5 screen/s) cuts', s['score'] == 1, f"score {s['score']}")
        await ev(page, f"__FS.spawn({{type:'orange', x:{cx}, y:{cy}, frozen:true}})")
        await swipe_through(page, cx, cy + r * 1.4)
        await tick(page, 0.2)
        s = await snap(page)
        R.check(f'[{dev}] Easy cutting: wider reach (1.4 x fruit size) cuts', s['score'] == 2)
        await ev(page, "__FS.setSetting('sens', 'normal')")
        await ev(page, f"__FS.spawn({{type:'orange', x:{cx}, y:{cy}, frozen:true}})")
        await ev(page, f'__swipe({cx - 150}, {cy}, {cx + 150}, {cy}, {300 / (0.5 * MIN)}, 30)')
        await tick(page, 300 / (0.5 * MIN) + 0.1)
        s = await snap(page)
        R.check(f'[{dev}] Normal cutting: the same calm swipe does not cut', s['score'] == 2)
        await ev(page, "__FS.setSetting('sens', 'precise')")
        await ev(page, f'__swipe({cx - 150}, {cy}, {cx + 150}, {cy}, {300 / (0.75 * MIN)}, 30)')
        await tick(page, 300 / (0.75 * MIN) + 0.1)
        s = await snap(page)
        R.check(f'[{dev}] Precise cutting: needs a faster swipe', s['score'] == 2)
        await ev(page, "__FS.setSetting('sens', 'normal'); __FS.setSetting('diff', 'normal'); __FS.setSetting('camView', 'show')")
        await page.evaluate("document.activeElement && document.activeElement.blur()")
        await page.keyboard.press('m')
        s = await snap(page)
        R.check(f'[{dev}] M key turns sound back on (was muted from version 1)', s['settings']['muted'] is False and not await page.evaluate("document.getElementById('btn-sound').classList.contains('muted')"))

        # ---------------------------------------------------------------- progress panel, blade colors, reset
        await ev(page, '__FS.menu()')
        await page.click('#btn-progress')
        s = await snap(page)
        n_ach = await page.locator('#ach-list li').count()
        n_done = await page.locator('#ach-list li.done').count()
        games = await page.locator('.stat .v').nth(0).text_content()
        R.check(f'[{dev}] Progress: 12 achievements listed, earned ones ticked, stats shown', s['ui']['progress'] and n_ach == 12 and n_done == len(s['ach']) and n_done >= 3 and int(games) >= 5, f"{n_done}/{n_ach}, games {games}, ach {s['ach']}")
        mango = page.locator('.swatch', has_text='Mango'); rainbow = page.locator('.swatch', has_text='Rainbow')
        R.check(f'[{dev}] unlocked blade colors can be picked, locked ones cannot', await mango.is_enabled() and not await rainbow.is_enabled())
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_progress.png')
        await mango.click()
        s = await snap(page)
        R.check(f'[{dev}] picking the Mango blade saves it', s['blade'] == 'mango' and json.loads(await page.evaluate("localStorage.getItem('fruitSlicer.progress')"))['blade'] == 'mango')
        await page.click('#progress-done')
        await page.click('#btn-settings'); await page.click('#btn-reset')
        R.check(f'[{dev}] Reset asks to confirm inside the panel', await page.is_visible('#reset-confirm'))
        await page.click('#btn-reset-no')
        s = await snap(page)
        R.check(f'[{dev}] Cancel keeps progress', not await page.is_visible('#reset-confirm') and len(s['ach']) >= 3)
        await page.click('#btn-reset'); await page.click('#btn-reset-yes')
        s = await snap(page)
        R.check(f'[{dev}] Delete clears scores, stats, achievements, blade', s['ach'] == [] and s['best'] == {'classic': 0, 'arcade': 0, 'zen': 0} and s['blade'] == 'classic')
        await page.click('#settings-done')

        # ---------------------------------------------------------------- soak: a bot plays every mode
        bot = """(secs) => {
          const dt = 1 / 30; let worst = 0;
          for (let i = 0; i < secs / dt; i++) {
            const s = __FS.snap();
            if (s.state === 'over' && s.resultsShown) { __FS.start(s.mode); }
            if (s.state === 'playing') {
              const tgt = s.items.filter(it => it.kind !== 'bomb' && it.y < s.H * 0.85 && it.y > 40);
              if (tgt.length && Math.random() < 0.5) {
                const f = tgt[Math.floor(Math.random() * tgt.length)], t = __FS.now();
                const id = 'bot' + i;
                __FS.point(id, f.x - 120, f.y - 30, t); __FS.point(id, f.x, f.y, t + 0.02); __FS.point(id, f.x + 120, f.y + 30, t + 0.04); __FS.end(id);
              }
            }
            __FS.tick(dt, 1);
            const n = s.particles + s.halves + s.splats;
            if (n > worst) worst = n;
          }
          return worst;
        }"""
        await ev(page, '__FS.seed(4242)'); await ev(page, '__FS.spawning(true)')
        worst = 0
        for m, secs in (('classic', 120), ('arcade', 90), ('zen', 90)):
            await to_playing(page, m)
            for _ in range(secs):   # 1 s of game time per call, so the browser draws in between
                worst = max(worst, await page.evaluate(bot, 1))
        s = await snap(page)
        R.check(f'[{dev}] soak 5 min across all modes: effects stay bounded', worst <= 520 + 80 + 26, f"max effects {worst}, sliced {s['stats']['sliced']}, power-ups {s['stats']['powers']}, combos {s['stats']['combos']}")
        errs = await page.evaluate('window.__FS_ERRORS || []')
        R.check(f'[{dev}] no frame errors during all play', not errs, str(errs[:2]))
        prog = json.loads(await page.evaluate("localStorage.getItem('fruitSlicer.progress')"))
        R.check(f'[{dev}] stats saved during play', prog['stats']['games'] >= 1 and prog['stats']['sliced'] > 50, json.dumps(prog['stats']))

        # ---------------------------------------------------------------- rotate during play
        await ev(page, '__FS.spawning(false)')
        await to_playing(page, 'classic')
        await ev(page, f"__FS.spawn({{type:'orange', x:{W * 0.8}, y:{H * 0.3}, frozen:true}})")
        await page.set_viewport_size({'width': height, 'height': width})
        await page.wait_for_function(f'__FS.snap().W === {height}', timeout=5000)
        s = await snap(page)
        it = s['items'][0]
        R.check(f'[{dev}] rotate mid-game: fruit rescaled and still on screen', s['W'] == height and 0 < it['x'] < s['W'] and 0 < it['y'] < s['H'], json.dumps(it))
        await ev(page, '__FS.menu()')
        await tick(page, 0.1)
        s = await snap(page)
        ok = all(0 < t['x'] - t['r'] and t['x'] + t['r'] < s['W'] and t['y'] + t['r'] < s['H'] for t in s['targets'])
        R.check(f'[{dev}] menu re-lays out after rotation', ok)
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_rotated_menu.png')
        await page.set_viewport_size({'width': width, 'height': height})
        await page.wait_for_timeout(200)

        # ---------------------------------------------------------------- leaving the app pauses
        await to_playing(page, 'arcade')
        await ev(page, "Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
        s = await snap(page)
        R.check(f'[{dev}] switching apps/tabs pauses the game', s['state'] == 'paused')
        await ev(page, "Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")

        # ---------------------------------------------------------------- a busy Arcade screenshot
        await ev(page, '__FS.resume()'); await ev(page, '__FS.spawning(true)'); await ev(page, '__FS.seed(99)')
        await ev(page, "__FS.power('freeze'); __FS.power('double')")
        for _ in range(3):
            await page.evaluate(bot, 1)
        s = await snap(page)
        fr = [i for i in s['items'] if i['kind'] == 'fruit' and 0 < i['y'] < H]
        if fr:
            f0 = fr[0]
            await ev(page, f"__swipe({f0['x'] - 200}, {f0['y'] - 60}, {f0['x'] + 200}, {f0['y'] + 60}, 0.1, 10)")
        await tick(page, 0.12)
        await page.screenshot(path=f'{OUT}/{TAG}_{dev}_playing.png')

        # ---------------------------------------------------------------- reload keeps settings and progress
        await page.reload()
        await page.wait_for_function('window.__FS !== undefined')
        s = await snap(page)
        R.check(f'[{dev}] after reload: settings and stats kept', s['settings']['muted'] is False and s['settings']['music'] == 20 and (await ev(page, '__FS.progress()'))['stats']['games'] >= 1)
        bad = problems(page)
        R.check(f'[{dev}] console clean (no errors or warnings)', not bad, ' | '.join(bad[:3]))
        await br.close()


async def main():
    R = Report(f'Suite A v2 logic ({TAG})')
    if ONLY in (None, 'desktop'):
        await suite(1280, 720, False, R)
    if ONLY in (None, 'phone'):
        await suite(412, 915, True, R)
    sys.exit(1 if R.summary() else 0)

asyncio.run(main())
