"""Test harness: real Chrome/Chromium + a fake camera (video file) + local copies of the CDN files.

Paths are relative to this repo. Run tests/get_assets.py once first (downloads the tracker, the hand model,
test photos, and builds the fake-camera videos). Settings you can override with environment variables:
  GAME_FILE    the page to test (default: index.html in the repo root, built by tools/build.py)
  CHROME_PATH  Chrome to use (default: google-chrome if installed, else Playwright's Chromium)
"""
import asyncio, json, os, pathlib, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests')
GAME_FILE = os.environ.get('GAME_FILE', os.path.join(ROOT, 'index.html'))
GAME = pathlib.Path(GAME_FILE).resolve().as_uri()
VENDOR = os.path.join(TESTS, 'vendor')
PKG = os.environ.get('MP_PACKAGE', os.path.join(VENDOR, 'tasks-vision'))          # @mediapipe/tasks-vision 1.1.1 package
MODEL = os.environ.get('HAND_MODEL', os.path.join(VENDOR, 'hand_landmarker.task'))  # official float16/1 hand model
FONTS = os.path.join(ROOT, 'src', 'fonts')
VIDEOS = os.path.join(TESTS, 'videos')
OUT = os.path.join(TESTS, 'out')
WWW_APP = os.path.join(OUT, 'www-app')
CHROME = os.environ.get('CHROME_PATH') or shutil.which('google-chrome') or shutil.which('google-chrome-stable') or None
os.makedirs(OUT, exist_ok=True)

FONT_CSS = """
@font-face{font-family:'Shrikhand';font-style:normal;font-weight:400;font-display:swap;src:url(https://fonts.gstatic.com/local/shrikhand-400.woff2) format('woff2');}
""" + ''.join(
    "@font-face{font-family:'Baloo 2';font-style:normal;font-weight:%d;font-display:swap;src:url(https://fonts.gstatic.com/local/baloo-%d.woff2) format('woff2');}\n" % (w, w)
    for w in (500, 600, 700, 800))
FONT_FILES = {
    'shrikhand-400.woff2': os.path.join(FONTS, 'shrikhand-latin-400-normal.woff2'),
    **{f'baloo-{w}.woff2': os.path.join(FONTS, f'baloo-2-latin-{w}-normal.woff2') for w in (500, 600, 700, 800)},
}

class Net:
    """Serves the CDN/model/font URLs from local files. Records every request.
    block_cdn: jsDelivr refuses; serve_unpkg: unpkg.com works (backup CDN), else it refuses too.
    local_base: an http://127.0.0.1 server whose requests pass through (or are refused if block_local)."""
    def __init__(self, block_model=False, block_cdn=False, serve_unpkg=False, local_base=None, block_local=False, corrupt_wasm=False):
        self.block_model, self.block_cdn, self.serve_unpkg, self.corrupt_wasm = block_model, block_cdn, serve_unpkg, corrupt_wasm
        self.local_base, self.block_local = local_base, block_local
        self.log = []

    async def handle(self, route):
        url = route.request.url
        self.log.append(url)
        cors = {'Access-Control-Allow-Origin': '*'}
        if url.startswith('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1/'):
            if self.block_cdn:
                return await route.abort('connectionrefused')
            rel = url.split('@1.1.1/', 1)[1].split('?')[0]
            path = os.path.join(PKG, rel)
            if self.corrupt_wasm and rel.endswith('.wasm'):
                return await route.fulfill(status=200, body='<!doctype html><title>Error</title>' + 'x' * 2000000, headers={**cors, 'Content-Type': 'text/html'})
            if os.path.isfile(path):
                ct = 'application/wasm' if path.endswith('.wasm') else 'text/javascript; charset=utf-8'
                return await route.fulfill(path=path, headers={**cors, 'Content-Type': ct})
            return await route.fulfill(status=404, body='not found', headers=cors)
        if url.startswith('https://unpkg.com/@mediapipe/tasks-vision@1.1.1/'):
            if not self.serve_unpkg:
                return await route.abort('connectionrefused')
            rel = url.split('@1.1.1/', 1)[1].split('?')[0]
            path = os.path.join(PKG, rel)
            if os.path.isfile(path):
                ct = 'application/wasm' if path.endswith('.wasm') else 'application/javascript; charset=utf-8'
                return await route.fulfill(path=path, headers={**cors, 'Content-Type': ct})
            return await route.fulfill(status=404, body='not found', headers=cors)
        if self.local_base and url.startswith(self.local_base):
            if self.block_local and ('/mp/' in url or '/models/' in url):
                return await route.abort('connectionrefused')
            return await route.continue_()
        if url.startswith('https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/'):
            if self.block_model:
                return await route.abort('connectionrefused')
            return await route.fulfill(path=MODEL, headers={**cors, 'Content-Type': 'application/octet-stream'})
        if url.startswith('https://fonts.googleapis.com/css2'):
            return await route.fulfill(status=200, body=FONT_CSS, headers={**cors, 'Content-Type': 'text/css'})
        if url.startswith('https://fonts.gstatic.com/local/'):
            name = url.rsplit('/', 1)[1]
            return await route.fulfill(path=FONT_FILES[name], headers={**cors, 'Content-Type': 'font/woff2'})
        if url.startswith('file://') or url.startswith('data:') or url.startswith('blob:'):
            return await route.continue_()
        return await route.abort('blockedbyclient')


async def launch(p, video=None, grant=True, extra_args=None, file_access=True):
    args = ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist',
            '--autoplay-policy=no-user-gesture-required']
    if file_access:
        args += ['--allow-file-access-from-files']
    if video:
        args += ['--use-fake-device-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(VIDEOS, video + '.y4m')]
    if grant:
        args += ['--use-fake-ui-for-media-stream']
    if extra_args:
        args += extra_args
    return await p.chromium.launch(executable_path=CHROME, headless=True, args=args)


async def open_game(browser, net, width=1280, height=720, mobile=False, dpr=1, hash_='#test', deny_camera=False, url=None, init_js=None):
    ctx = await browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=dpr,
                                    is_mobile=mobile, has_touch=mobile)
    if deny_camera:
        pass
    page = await ctx.new_page()
    page.console_log = []
    page.on('console', lambda m: page.console_log.append(f'[{m.type}] {m.text}'))
    page.on('pageerror', lambda e: page.console_log.append(f'[pageerror] {e}'))
    await page.route('**/*', net.handle)
    if init_js:
        await page.add_init_script(init_js)
    await page.goto((url or GAME) + hash_)
    await page.wait_for_function('window.__FS !== undefined', timeout=10000)
    return ctx, page


async def snap(page):
    return await page.evaluate('window.__FS.snap()')


async def wait_state(page, st, timeout=60000):
    await page.wait_for_function(f"window.__FS.snap().state === {json.dumps(st)}", timeout=timeout)


def problems(page, allow=()):
    """Console errors/warnings that are not expected."""
    bad = []
    for line in page.console_log:
        if line.startswith('[error]') or line.startswith('[pageerror]') or line.startswith('[warning]'):
            if any(a in line for a in allow):
                continue
            bad.append(line)
    return bad


class Report:
    def __init__(self, name):
        self.name, self.rows = name, []

    def check(self, label, ok, detail=''):
        self.rows.append((bool(ok), label, detail))
        print(('PASS ' if ok else 'FAIL ') + label + (f'  [{detail}]' if detail else ''), flush=True)
        return ok

    def summary(self):
        n = len(self.rows); f = sum(1 for r in self.rows if not r[0])
        print(f'== {self.name}: {n - f}/{n} passed' + (f', {f} FAILED' if f else ''), flush=True)
        return f


# ---------------------------------------------------------------- a small web server (http://127.0.0.1 counts as a secure page)
import http.server, threading, functools, socketserver
class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.wasm': 'application/wasm', '.task': 'application/octet-stream',
                      '.js': 'text/javascript', '.html': 'text/html; charset=utf-8'}
    def log_message(self, *a):
        pass

def serve_dir(directory, port=0):
    """Serves a folder at http://127.0.0.1:<port>/ in a background thread. Returns (base_url, server)."""
    handler = functools.partial(_Handler, directory=directory)
    srv = socketserver.ThreadingTCPServer(('127.0.0.1', port), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{srv.server_address[1]}/', srv


def prepare_www_app():
    """Folder that looks like the Android app's web files: app page + bundled tracker + model (built by tools/build.py)."""
    page = os.path.join(WWW_APP, 'index.html')
    if not os.path.exists(page):
        raise SystemExit('tests/out/www-app/index.html is missing: run python tools/build.py first')
    for rel in ('vision_bundle.js', 'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm',
                'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm'):
        dst = os.path.join(WWW_APP, 'mp', rel)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(PKG, rel), dst)
    dst = os.path.join(WWW_APP, 'models', 'hand_landmarker.task')
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(MODEL, dst)
    return WWW_APP
