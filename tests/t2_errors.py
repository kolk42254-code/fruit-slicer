"""Suite C (v2): what the player sees when something goes wrong, and that they can always recover."""
import asyncio, json, sys
from playwright.async_api import async_playwright
from harness import *

TAG = sys.argv[1] if len(sys.argv) > 1 else 'r1'
MP_NOISE = ('gl_context.cc', 'landmark_projection_calculator', 'inference_feedback_manager', 'XNNPACK')

async def to_menu_with_camera(page, timeout=180000):
    await page.click('#btn-camera')
    await wait_state(page, 'menu', timeout=timeout)

async def main():
    R = Report(f'Suite C v2 errors ({TAG})')
    async with async_playwright() as p:
        # 1) camera permission denied
        br = await launch(p, video='static_one', grant=False)
        ctx, page = await open_game(br, Net(), 1280, 720)
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=60000)
        s = await snap(page)
        R.check('[denied] "Camera is blocked" with fix steps', s['ui']['errTitle'] == 'Camera is blocked' and s['ui']['error'], s['ui']['errTitle'])
        await page.screenshot(path=f'{OUT}/{TAG}_err_denied.png')
        await page.click('#btn-err-pointer')
        s = await snap(page)
        R.check('[denied] "Play with mouse or touch" still works', s['state'] == 'menu' and s['inputMode'] == 'pointer' and not s['camOn'] and not s['ui']['error'])
        R.check('[denied] menu offers "Use camera instead"', await page.is_visible('#btn-use-camera'))
        await br.close()

        # 2) no camera on the device
        br = await launch(p, video=None, grant=True)
        ctx, page = await open_game(br, Net(), 1280, 720)
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=60000)
        s = await snap(page)
        R.check('[no camera] clear message', s['ui']['errTitle'] in ('No camera found', 'Camera did not start'), s['ui']['errTitle'])
        await page.click('#btn-err-pointer')
        await page.click('#btn-settings'); await page.click('#btn-check')
        await wait_state(page, 'error', timeout=60000)
        s = await snap(page)
        R.check('[no camera] "Check hand tracking": Settings closes, same clear message, no check screen',
                s['ui']['errTitle'] in ('No camera found', 'Camera did not start') and not s['ui']['settings'] and not s['ui']['check'] and not s['ui']['checkTip'], s['ui']['errTitle'])
        await page.click('#btn-err-pointer')
        s = await snap(page)
        R.check('[no camera] then "Play with mouse or touch" goes back to the menu', s['state'] == 'menu' and s['inputMode'] == 'pointer' and not s['ui']['check'] and s['ui']['menuBar'])
        await br.close()

        # 2b) tracking check while the hand tracker cannot download
        br = await launch(p, video='static_one')
        net = Net(block_model=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await page.click('#btn-pointer')
        await page.click('#btn-settings'); await page.click('#btn-check')
        await wait_state(page, 'error', timeout=90000)
        s = await snap(page)
        R.check('[check, offline model] "Hand tracker did not load", no check screen', s['ui']['errTitle'] == 'Hand tracker did not load' and not s['ui']['check'], s['ui']['errTitle'])
        net.block_model = False
        await page.click('#btn-retry')
        await wait_state(page, 'check', timeout=180000)
        s = await snap(page)
        R.check('[check, offline model] "Try again" recovers and opens the tracking check', s['ui']['check'] and s['camOn'], s['state'])
        await ctx.close()
        # a failed check must not send a later camera start to the check screen
        net = Net(block_model=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await page.click('#btn-pointer')
        await page.click('#btn-settings'); await page.click('#btn-check')
        await wait_state(page, 'error', timeout=90000)
        await page.click('#btn-err-pointer')
        net.block_model = False
        await page.click('#btn-use-camera')
        await wait_state(page, 'menu', timeout=180000)
        await page.wait_for_timeout(1000)
        s = await snap(page)
        R.check('[check, offline model] later "Use camera instead" from the menu goes to the menu as usual', s['state'] == 'menu' and s['camOn'] and not s['ui']['check'], s['state'])
        await br.close()

        # 3) hand model download fails, then works on "Try again"
        br = await launch(p, video='static_one')
        net = Net(block_model=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=90000)
        s = await snap(page)
        R.check('[offline model] "Hand tracker did not load"', s['ui']['errTitle'] == 'Hand tracker did not load', s['ui']['errTitle'])
        await page.screenshot(path=f'{OUT}/{TAG}_err_tracker.png')
        net.block_model = False
        await page.click('#btn-retry')
        await wait_state(page, 'menu', timeout=180000)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[offline model] Try again recovers and tracks the hand', s['camOn'] and len(s['hands']) == 1, json.dumps(s['hands'])[:150])
        tries = [u for u in net.log if 'hand_landmarker.task' in u]
        R.check('[offline model] backup model address tried after the first fails', any('/latest/' in u for u in tries) and any('/1/' in u for u in tries), str([u.split('float16/')[1] for u in tries]))
        await br.close()

        # 4) both code CDNs blocked, then jsDelivr works on "Try again"
        br = await launch(p, video='static_one')
        net = Net(block_cdn=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=90000)
        s = await snap(page)
        R.check('[offline code] "Hand tracker did not load"', s['ui']['errTitle'] == 'Hand tracker did not load', s['ui']['errTitle'])
        R.check('[offline code] backup CDN (unpkg) was tried', any(u.startswith('https://unpkg.com/') for u in net.log))
        net.block_cdn = False
        await page.click('#btn-retry')
        await wait_state(page, 'menu', timeout=180000)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[offline code] Try again recovers', s['camOn'] and len(s['hands']) == 1)
        await br.close()

        # 5) jsDelivr blocked, unpkg works: no error at all
        br = await launch(p, video='static_one')
        net = Net(block_cdn=True, serve_unpkg=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await to_menu_with_camera(page)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[jsDelivr down] game loads the tracker from the backup CDN', s['state'] == 'menu' and len(s['hands']) == 1 and any(u.startswith('https://unpkg.com/') for u in net.log))
        await br.close()

        # 6) first CDN sends a broken file (an error page): caught, backup CDN used
        br = await launch(p, video='static_one')
        net = Net(corrupt_wasm=True, serve_unpkg=True)
        ctx, page = await open_game(br, net, 1280, 720)
        await to_menu_with_camera(page)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[broken download] bad file is rejected and the backup copy is used', s['state'] == 'menu' and len(s['hands']) == 1 and any(u.startswith('https://unpkg.com/') and u.endswith('.wasm') for u in net.log))
        await br.close()

        # 7) page not secure (e.g. opened from a phone file manager)
        br = await launch(p, video='static_one')
        ctx, page = await open_game(br, Net(), 412, 915, mobile=True)
        await page.evaluate("Object.defineProperty(window, 'isSecureContext', {get: () => false})")
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=30000)
        s = await snap(page)
        R.check('[not secure] explains https is needed', s['ui']['errTitle'] == 'Camera not allowed here', s['ui']['errTitle'])
        await page.screenshot(path=f'{OUT}/{TAG}_err_insecure_phone.png')
        await br.close()

        # 8) camera unplugged in the middle of a game
        br = await launch(p, video='static_one')
        ctx, page = await open_game(br, Net(), 1280, 720)
        await to_menu_with_camera(page)
        await page.evaluate("__FS.start('arcade')")
        await wait_state(page, 'playing', timeout=30000)
        await page.evaluate("document.getElementById('cam').srcObject.getVideoTracks().forEach(t => t.dispatchEvent(new Event('ended')))")
        await page.wait_for_timeout(300)
        s = await snap(page)
        R.check('[unplugged] game pauses and shows "Camera stopped"', s['ui']['errTitle'] == 'Camera stopped' and s['state'] == 'error', f"{s['state']} / {s['ui']['errTitle']}")
        await page.click('#btn-retry')
        await wait_state(page, 'menu', timeout=60000)
        await page.wait_for_timeout(2000)
        s = await snap(page)
        R.check('[unplugged] Try again brings the camera back and tracks', s['camOn'] and len(s['hands']) == 1)
        bad = problems(page, allow=MP_NOISE + ('Fruit Slicer: camera failed',))
        R.check('[unplugged] no unexpected console errors', not bad, ' | '.join(bad[:3]))
        await br.close()

        # 9) the app: its own tracker files missing -> uses the internet copy
        base, srv = serve_dir(prepare_www_app())
        br = await launch(p, video='static_one')
        net = Net(local_base=base, block_local=True)
        ctx, page = await open_game(br, net, 412, 915, mobile=True, url=base + 'index.html')
        await to_menu_with_camera(page)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[app, files missing] falls back to the online tracker', s['state'] == 'menu' and s['trackerSource'] == 'cdn' and len(s['hands']) == 1, s['trackerSource'])
        await br.close()

        # 10) the app with no internet and no files: clear message, touch still works
        br = await launch(p, video='static_one')
        net = Net(local_base=base, block_local=True, block_cdn=True, block_model=True)
        ctx, page = await open_game(br, net, 412, 915, mobile=True, url=base + 'index.html')
        await page.click('#btn-camera')
        await wait_state(page, 'error', timeout=90000)
        s = await snap(page)
        msg = await page.text_content('#err-msg')
        R.check('[app, nothing loads] message offers touch play', s['ui']['errTitle'] == 'Hand tracker did not load' and 'touch' in msg, msg)
        await page.click('#btn-err-pointer')
        s = await snap(page)
        R.check('[app, nothing loads] touch play works', s['state'] == 'menu' and s['inputMode'] == 'pointer')
        await br.close()
        srv.shutdown()

        # 11) browser without background threads -> main thread
        br = await launch(p, video='static_one')
        ctx, page = await open_game(br, Net(), 1280, 720, init_js="delete window.Worker; window.Worker = undefined;")
        await to_menu_with_camera(page)
        await page.wait_for_timeout(3000)
        s = await snap(page)
        R.check('[no Worker support] tracker runs on the main thread and works', s['trackerKind'] == 'main' and len(s['hands']) == 1, s['trackerKind'])
        await br.close()
    sys.exit(1 if R.summary() else 0)

asyncio.run(main())
