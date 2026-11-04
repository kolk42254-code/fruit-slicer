"""v2 real-time soak: camera on (background tracker), Arcade with power-ups and music, a bot slicing live.
Frame rate and memory must stay steady, the tracker must keep answering."""
import asyncio, json, sys, time
from playwright.async_api import async_playwright
from harness import *
MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 4
TAG = sys.argv[2] if len(sys.argv) > 2 else 'r1'
BOT = """() => {
  window.__botTimer = setInterval(() => {
    const s = __FS.snap();
    if (s.state === 'over' && s.resultsShown) { __FS.start(['classic', 'arcade', 'zen'][Math.floor(Math.random() * 3)]); return; }
    if (s.state !== 'playing') return;
    const tgt = s.items.filter(it => it.kind !== 'bomb' && it.y < s.H * 0.85 && it.y > 40);
    if (!tgt.length || Math.random() < 0.3) return;
    const f = tgt[Math.floor(Math.random() * tgt.length)], t = __FS.now(), id = 'rt' + Math.random();
    __FS.point(id, f.x - 120, f.y - 30, t); __FS.point(id, f.x, f.y, t + 0.02); __FS.point(id, f.x + 120, f.y + 30, t + 0.04); __FS.end(id);
  }, 120);
}"""
async def rate(page):
    return await page.evaluate("new Promise(r => { let n = 0; const t0 = performance.now(); (function f(){ n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else r(n / 2); })(); })")
async def main():
    R = Report(f'v2 real-time soak with camera, {MINUTES} min ({TAG})')
    async with async_playwright() as p:
        br = await launch(p, video='static_one')
        ctx, page = await open_game(br, Net(), 1280, 720)
        await page.click('#btn-camera')
        await wait_state(page, 'menu', timeout=180000)
        await page.evaluate("__FS.seed(31337); __FS.start('arcade')")
        await page.wait_for_timeout(3000)
        await page.evaluate(BOT)
        await page.wait_for_timeout(8000)
        first = await rate(page)
        s0 = await snap(page)
        heap0 = await page.evaluate('performance.memory ? performance.memory.usedJSHeapSize : 0')
        print(f'start: {first} frames/s, heap {heap0/1e6:.1f} MB, music {s0["musicOn"]}, tracker {s0["trackerKind"]} {s0["detectCount"]} frames', flush=True)
        rates, heaps, counts = [], [], []
        t_end = time.time() + MINUTES * 60
        while time.time() < t_end:
            await page.wait_for_timeout(20000)
            r_ = await rate(page); s = await snap(page)
            heap = await page.evaluate('performance.memory ? performance.memory.usedJSHeapSize : 0')
            rates.append(r_); heaps.append(heap); counts.append(s['detectCount'])
            print(f'  {r_:5.1f} frames/s  heap {heap/1e6:6.1f} MB  {s["mode"]:7s} {s["state"]:8s} sliced {s["stats"]["sliced"]:4d} powers {s["stats"]["powers"]:3d} tracker frames {s["detectCount"]:5d} hands {len(s["hands"])} items {len(s["items"])}', flush=True)
        last = sum(rates[-2:]) / 2
        await page.evaluate('clearInterval(window.__botTimer)')
        heap1 = min(heaps[-2:])
        s = await snap(page)
        R.check('frame rate does not drop over time (end >= 75% of start)', last >= 0.75 * first, f'start {first}, end {last:.1f} frames/s')
        R.check('memory does not keep growing (< +15 MB)', heap1 - heap0 < 15e6, f'heap {heap0/1e6:.1f} -> {heap1/1e6:.1f} MB')
        R.check('hand tracker kept answering the whole time', all(b > a for a, b in zip(counts, counts[1:])) and not s['trackingDead'] and len(s['hands']) == 1, str(counts))
        R.check('game kept running, slicing and using power-ups', s['stats']['sliced'] > 50 and s['stats']['powers'] >= 1, f"sliced {s['stats']['sliced']}, power-ups {s['stats']['powers']}")
        R.check('no frame errors', not await page.evaluate('window.__FS_ERRORS || []'))
        bad = problems(page, allow=('gl_context.cc', 'landmark_projection_calculator', 'inference_feedback_manager', 'XNNPACK'))
        R.check('console clean', not bad, ' | '.join(bad[:2]))
        await br.close()
    sys.exit(1 if R.summary() else 0)
asyncio.run(main())
