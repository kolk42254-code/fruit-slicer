// Builds the app's web folder (app/www) from the website's index.html, so the app and the website run the same game.
// The hand tracker (MediaPipe Tasks Vision code + the hand model) is copied in, so the app works with no internet.
//   node scripts/prepare-www.mjs                 downloads the official hand model
//   MODEL_FILE=/path/hand_landmarker.task node scripts/prepare-www.mjs   uses a local copy instead
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.resolve(here, '..');
const www = path.join(app, 'www');
const mp = path.join(app, 'node_modules', '@mediapipe', 'tasks-vision');
const MODEL_URLS = [
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task'
];
const TRACKER_FILES = ['vision_bundle.js', 'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm',
  'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm'];

function fail(msg) {
  console.error('prepare-www: ' + msg);
  process.exit(1);
}
const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');

fs.rmSync(www, { recursive: true, force: true });
fs.mkdirSync(path.join(www, 'mp', 'wasm'), { recursive: true });
fs.mkdirSync(path.join(www, 'models'), { recursive: true });

// 1) the game page, switched to the tracker files inside the app
const page = fs.readFileSync(path.join(app, '..', 'index.html'), 'utf8');
const tag = '<meta name="fs-assets" content="cdn">';
if (page.split(tag).length !== 2) fail('index.html must contain ' + tag + ' exactly once');
fs.writeFileSync(path.join(www, 'index.html'), page.replace(tag, '<meta name="fs-assets" content="local">'));

// 2) hand tracker code: must be the same version the website loads from the CDN
const installed = JSON.parse(fs.readFileSync(path.join(mp, 'package.json'), 'utf8')).version;
const wanted = (page.match(/const MP_VERSION = '([^']+)'/) || [])[1];
if (installed !== wanted) fail(`@mediapipe/tasks-vision ${installed} is installed but the game expects ${wanted}`);
for (const f of TRACKER_FILES) fs.copyFileSync(path.join(mp, f), path.join(www, 'mp', f));

// 3) the hand model
async function getModel() {
  if (process.env.MODEL_FILE) return fs.readFileSync(process.env.MODEL_FILE);
  for (const url of MODEL_URLS) {
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return Buffer.from(await res.arrayBuffer());
      } catch (err) {
        console.warn(`prepare-www: model download failed (${url}, try ${attempt}): ${err.message}`);
        await new Promise((r) => setTimeout(r, 2000 * attempt));
      }
    }
  }
  return fail('could not download the hand model');
}
const model = await getModel();
// a .task file is a zip archive holding the two TFLite models of the hand landmarker
if (model.length < 1e6 || !model.includes('hand_detector.tflite') || !model.includes('hand_landmarks_detector.tflite')) {
  fail('the hand model file looks wrong (' + model.length + ' bytes)');
}
fs.writeFileSync(path.join(www, 'models', 'hand_landmarker.task'), model);

// 4) licences of the bundled parts (hand tracker, fonts, Capacitor)
fs.cpSync(path.join(app, '..', 'licenses'), path.join(www, 'licenses'), { recursive: true });

let total = 0;
const list = ['index.html', ...TRACKER_FILES.map((f) => 'mp/' + f), 'models/hand_landmarker.task'];
for (const f of list) {
  const buf = fs.readFileSync(path.join(www, f));
  total += buf.length;
  console.log(`  ${f.padEnd(40)} ${String(buf.length).padStart(10)} bytes  sha256 ${sha256(buf).slice(0, 16)}`);
}
console.log(`prepare-www: www ready, ${(total / 1048576).toFixed(1)} MB, tracker ${installed}`);
