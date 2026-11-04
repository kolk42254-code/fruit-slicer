// Drives the app's WebView on the Android emulator over the Chrome DevTools Protocol and checks the game works.
//   node cdp-test.mjs <out-dir> debug        full check (camera permission already granted)
//   node cdp-test.mjs <out-dir> permission   camera permission not granted yet: allow it in the Android dialog
import fs from 'node:fs';
import { execSync } from 'node:child_process';

const OUT = process.argv[2] || 'ci-out';
const MODE = process.argv[3] || 'debug';
const PKG = 'io.github.kolk42254code.fruitslicer.test';                // the debug APK ("Fruit Slicer TEST"): own ID
const ACTIVITY = 'io.github.kolk42254code.fruitslicer.MainActivity';   // the activity class keeps its name
const results = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (s) => { console.log(s); fs.appendFileSync(`${OUT}/results.txt`, s + '\n'); };
const check = (name, ok, detail = '') => {
  results.push({ mode: MODE, name, ok: !!ok, detail: String(detail) });
  log(`${ok ? 'PASS' : 'FAIL'} [${MODE}] ${name}${detail !== '' ? '  [' + detail + ']' : ''}`);
  return ok;
};
const adb = (args) => execSync(`adb ${args}`, { encoding: 'utf8', timeout: 60000 });

async function findPage() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
      const page = list.find((t) => t.type === 'page' && /localhost/.test(t.url));
      if (page) return page;
    } catch (err) { /* not ready yet */ }
    await sleep(1000);
  }
  throw new Error('no WebView page found on the DevTools socket');
}

class CDP {
  constructor(url) { this.url = url; this.id = 0; this.pending = new Map(); this.console = []; }
  open() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error('DevTools websocket error'));
      this.ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.id && this.pending.has(m.id)) {
          const p = this.pending.get(m.id);
          this.pending.delete(m.id);
          if (m.error) p.reject(new Error(m.error.message)); else p.resolve(m.result);
        } else if (m.method === 'Runtime.consoleAPICalled') {
          this.console.push(`[${m.params.type}] ` + m.params.args.map((a) => (a.value !== undefined ? a.value : a.description || '')).join(' '));
        } else if (m.method === 'Runtime.exceptionThrown') {
          const d = m.params.exceptionDetails;
          this.console.push('[exception] ' + ((d.exception && d.exception.description) || d.text));
        }
      };
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('DevTools timeout: ' + method)); } }, 120000);
    });
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text);
    return r.result.value;
  }
  async shot(name) {
    try {
      const r = await this.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(`${OUT}/${MODE}_${name}.png`, Buffer.from(r.data, 'base64'));
    } catch (err) { log('screenshot failed: ' + err.message); }
  }
}

async function waitFor(fn, ms, every = 500) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await fn()) return true; } catch (err) { /* page may be reloading */ }
    await sleep(every);
  }
  return false;
}

function uiDump() {
  adb('shell uiautomator dump /sdcard/ui.xml');
  return adb('shell cat /sdcard/ui.xml');
}
function tapBounds(n) {
  const b = n.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
  if (!b) return false;
  adb(`shell input tap ${Math.round((+b[1] + +b[3]) / 2)} ${Math.round((+b[2] + +b[4]) / 2)}`);
  return true;
}
// The emulator is slow (software graphics), so its own launcher sometimes shows "Pixel Launcher isn't responding".
// That system dialog would swallow our key presses and taps, so tap its "Wait" button first.
function dismissSystemDialogs(xml) {
  try {
    xml = xml || uiDump();
    if (!/isn.t responding/i.test(xml)) return false;
    const n = (xml.match(/<node [^>]*>/g) || []).find((x) => /resource-id="android:id\/aerr_wait"/.test(x) || / text="Wait"/.test(x));
    if (n && tapBounds(n)) { log('note: closed an emulator "isn\'t responding" dialog (not this app)'); execSync('sleep 1'); return true; }
  } catch (err) { /* dump can fail while the screen changes */ }
  return false;
}

// tap a native Android control (e.g. the permission dialog button) found by text or resource id
function tapNative(re) {
  for (let i = 0; i < 15; i++) {
    try {
      const xml = uiDump();
      if (dismissSystemDialogs(xml)) continue;
      for (const n of xml.match(/<node [^>]*>/g) || []) {
        const text = (n.match(/ text="([^"]*)"/) || [])[1] || '';
        const rid = (n.match(/ resource-id="([^"]*)"/) || [])[1] || '';
        if (re.test(text) || re.test(rid)) {
          const b = n.match(/bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
          if (b) {
            adb(`shell input tap ${Math.round((+b[1] + +b[3]) / 2)} ${Math.round((+b[2] + +b[4]) / 2)}`);
            return text || rid;
          }
        }
      }
    } catch (err) { /* dump can fail while the screen changes */ }
    execSync('sleep 1');
  }
  return null;
}

async function startCameraAndWait(cdp, allowDialog) {
  await cdp.eval("document.getElementById('btn-camera').click(); true");
  if (allowDialog) {
    await sleep(2500);
    adb(`exec-out screencap -p > ${OUT}/${MODE}_dialog.png`);
    const tapped = tapNative(/permission_allow_foreground_only_button|permission_allow_button|While using the app|Only this time|^Allow$/i);
    check('Android asks for the camera and "Allow" can be tapped', !!tapped, tapped || 'no dialog button found');
  }
  const t0 = Date.now();
  let s = null;
  while (Date.now() - t0 < 240000) {
    s = await cdp.eval('__FS.snap()');
    if (s.state === 'menu' || s.state === 'error') break;
    await sleep(1000);
  }
  log(`camera + hand tracker start took ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  return s;
}

async function main() {
  const page = await findPage();
  const cdp = new CDP(page.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  const ready = await waitFor(() => cdp.eval("document.readyState === 'complete' && !!document.getElementById('btn-camera')"), 60000);
  check('app opens and the game page loads', ready);

  if (MODE === 'debug') {
    check('start screen is shown', await cdp.eval("!document.getElementById('intro').hidden"));
    check('app page is set to the bundled (offline) tracker files', (await cdp.eval("document.querySelector('meta[name=fs-assets]').content")) === 'local');
    const cam = await cdp.eval("({ poster: document.getElementById('cam').poster.slice(0, 14), opacity: getComputedStyle(document.getElementById('cam')).opacity })");
    check('no grey video placeholder before the camera starts', cam.poster === 'data:image/gif' && cam.opacity === '0', JSON.stringify(cam));
    const info = await cdp.eval(`({ ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio,
      cssTop: getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-top'),
      hudPad: getComputedStyle(document.getElementById('hud')).paddingTop, title: document.title })`);
    log('device: ' + JSON.stringify(info));
    await cdp.shot('01_intro');
  }

  // test hooks are only on with #test in the address
  await cdp.eval("location.hash = '#test'; location.reload(); true");
  await sleep(3000);
  check('test mode loads', await waitFor(() => cdp.eval("typeof window.__FS === 'object'"), 60000));

  let s = await startCameraAndWait(cdp, MODE === 'permission');
  const errText = s && s.state === 'error' ? s.ui.errTitle + ': ' + (await cdp.eval("document.getElementById('err-msg').textContent")) : '';
  check('camera turns on and the hand tracker starts (menu reached)', s && s.state === 'menu', errText || (s && s.state));
  if (!s || s.state !== 'menu') return finish(cdp);
  check('hand tracker comes from inside the app (works offline)', s.trackerSource === 'local', s.trackerSource);
  check('hand tracker runs in a background thread', s.trackerKind === 'worker', s.trackerKind);
  check('camera picture arrives', s.camOn && s.video.w > 0, JSON.stringify(s.video));
  await cdp.shot('02_menu');

  if (MODE === 'permission') return finish(cdp);

  await sleep(10000);
  s = await cdp.eval('__FS.snap()');
  check('tracker keeps processing camera frames', s.detectCount >= 5 && !s.trackingDead,
    `${s.detectCount} frames, ${s.detectMs} ms each, page ${s.fps} fps, ${s.delegate}, ${s.gpuName}`);

  // a photo of a hand through the real tracker on this phone
  const jpg = fs.readFileSync(new URL('./hand.jpg', import.meta.url)).toString('base64');
  const res = await cdp.eval(`(async () => {
    const img = new Image(); img.src = 'data:image/jpeg;base64,${jpg}'; await img.decode();
    __FS.feedOnly(true); __FS.setVideoSize(640, 480); __FS.manual(true); __FS.spawning(false); __FS.start('classic'); __FS.tick(1 / 60, 120);
    let tips = null;
    for (let i = 0; i < 4; i++) { tips = await __FS.feed(img, __FS.now()); __FS.tick(1 / 30, 1); }
    const s = __FS.snap(), exp = __FS.toScreen(409.7 / 640, 175.5 / 480);
    return { tips: tips && tips.length, hand: s.hands[0] ? [s.hands[0].sx, s.hands[0].sy] : null, exp: [exp.x, exp.y], state: s.state };
  })()`);
  const err = res.hand ? Math.hypot(res.hand[0] - res.exp[0], res.hand[1] - res.exp[1]) : 999;
  check('hand photo: hand found and the cursor sits on the fingertip (< 10 px)', res.tips === 1 && err < 10,
    `error ${err.toFixed(1)} px, cursor ${JSON.stringify(res.hand && res.hand.map(Math.round))}, expected ${JSON.stringify(res.exp.map(Math.round))}`);

  const score = await cdp.eval(`(() => { const s = __FS.snap(); __FS.spawn({ type: 'orange', x: s.W / 2, y: s.H / 2, frozen: true }); const t = __FS.now();
    for (let i = 0; i <= 8; i++) __FS.point('sw', s.W / 2 - 150 + 300 * i / 8, s.H / 2, t + 0.1 * i / 8); __FS.end('sw'); __FS.tick(1 / 60, 20); return __FS.snap().score; })()`);
  check('a swipe through a fruit scores a point', score === 1, `score ${score}`);
  await cdp.shot('03_game');

  // phone Back button: pause, then menu, then leave the app (camera off), then come back (camera on)
  await cdp.eval('__FS.feedOnly(false); __FS.manual(false); true');
  if (dismissSystemDialogs()) { await sleep(1500); }
  await cdp.eval("__FS.snap().state === 'paused' && __FS.resume(); true"); // a system dialog on top pauses the game
  adb('shell input keyevent KEYCODE_BACK');
  await sleep(1500);
  s = await cdp.eval('__FS.snap()');
  check('Back button pauses the game', s.state === 'paused', s.state);
  await cdp.shot('04_paused');
  dismissSystemDialogs();
  adb('shell input keyevent KEYCODE_BACK');
  await sleep(1500);
  s = await cdp.eval('__FS.snap()');
  check('Back again goes to the menu', s.state === 'menu', s.state);
  dismissSystemDialogs();
  adb('shell input keyevent KEYCODE_BACK');
  let away = null;
  for (let i = 0; i < 20; i++) { // up to 10 s
    await sleep(500);
    away = await cdp.eval('({ hidden: document.hidden, tracks: __FS.snap().camTracks, asleep: __FS.snap().camAsleep })');
    if (away.asleep) { away.after = (i + 1) * 0.5 + ' s'; break; }
  }
  try { log('top activity after Back: ' + adb('shell dumpsys activity activities | grep -m1 topResumedActivity').trim()); } catch (err) { /* grep found nothing */ }
  try { log('app lifecycle: ' + adb('shell "logcat -d -s Capacitor:D | tail -6"').replace(/\s+/g, ' ').slice(-400)); } catch (err) { /* no log */ }
  check('Back in the menu leaves the app and turns the camera off', away.tracks === 0 && away.asleep === true, JSON.stringify(away));
  adb(`shell am start -n ${PKG}/${ACTIVITY}`);
  await sleep(7000);
  const back = await cdp.eval('({ hidden: document.hidden, tracks: __FS.snap().camTracks, camOn: __FS.snap().camOn, state: __FS.snap().state })');
  check('opening the app again turns the camera back on', back.hidden === false && back.tracks === 1 && back.camOn, JSON.stringify(back));
  await cdp.shot('05_back_again');

  // the tracking check screen (Settings > Check hand tracking) in a real Android WebView
  dismissSystemDialogs();
  await cdp.eval("__FS.menu(); __FS.check(); true");
  await sleep(5000);
  s = await cdp.eval('__FS.snap()');
  check('tracking check opens with live numbers', s.state === 'check' && s.ui.check && /results\/s/.test(s.ui.checkRows.trk) && !/^…/.test(s.ui.checkRows.trk),
    JSON.stringify(s.ui.checkRows));
  await cdp.shot('06_check');
  const chk = await cdp.eval(`(async () => {
    const img = new Image(); img.src = 'data:image/jpeg;base64,${jpg}'; await img.decode();
    __FS.feedOnly(true); __FS.setVideoSize(640, 480); __FS.manual(true);
    for (let i = 0; i < 4; i++) { await __FS.feed(img, __FS.now()); __FS.tick(1 / 30, 1); }
    __FS.refreshCheck();
    const n = __FS.checkNumbers();
    return { hands: n.hands, can: n.can, camSays: n.camSays, capTime: n.capTime, rows: __FS.snap().ui.checkRows };
  })()`);
  check('tracking check: the hand photo shows one hand with its size (about 35%) and sure score',
    chk.hands.length === 1 && Math.abs(chk.hands[0].size - 0.347) < 0.03 && chk.hands[0].sure > 0.5, JSON.stringify(chk.hands));
  log('camera details here: ' + JSON.stringify({ can: chk.can, camSays: chk.camSays, capTime: chk.capTime }));
  await cdp.shot('07_check_hand');
  const copy = await cdp.eval(`(async () => {
    document.getElementById('btn-check-copy').click();
    await new Promise((r) => setTimeout(r, 1000));
    return { note: document.getElementById('check-note').textContent, shown: !document.getElementById('check-text').hidden, report: __FS.report() };
  })()`);
  check('Copy report: copied, or shown to copy by hand', /copied/.test(copy.note) ? !copy.shown : copy.shown && /Could not copy/.test(copy.note), copy.note);
  check('report names the app and its own tracker files', /\(app\)/.test(copy.report) && /from local/.test(copy.report), copy.report.split('\n')[1]);
  log('tracking report on this emulator:\n' + copy.report);
  await cdp.eval('__FS.feedOnly(false); __FS.manual(false); true');
  dismissSystemDialogs();
  adb('shell input keyevent KEYCODE_BACK');
  await sleep(1500);
  s = await cdp.eval('__FS.snap()');
  check('Back button closes the tracking check', s.state === 'menu' && !s.ui.check, s.state);
  return finish(cdp);
}

function finish(cdp) {
  // MediaPipe info lines, and Capacitor's own safe-area helper when it runs while the page reloads (the game uses env() instead)
  const noise = /gl_context|landmark_projection|inference_feedback|XNNPACK|OpenGL error checking|Graph successfully|GL version|Error injecting safe area CSS/;
  const bad = cdp.console.filter((l) => /^\[(error|exception)\]/.test(l) && !noise.test(l));
  check('no unexpected errors in the page console', bad.length === 0, bad.slice(0, 3).join(' | '));
  fs.writeFileSync(`${OUT}/console_${MODE}.txt`, cdp.console.join('\n'));
  fs.writeFileSync(`${OUT}/results_${MODE}.json`, JSON.stringify(results, null, 1));
  const failed = results.filter((r) => !r.ok).length;
  log(`== emulator [${MODE}]: ${results.length - failed}/${results.length} passed`);
  try { cdp.ws.close(); } catch (err) { /* ignore */ }
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  check('test script ran without crashing', false, err.message);
  fs.writeFileSync(`${OUT}/results_${MODE}.json`, JSON.stringify(results, null, 1));
  process.exit(1);
});
