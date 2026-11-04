"""Renders the Android app icon and start-screen pictures with the game's own fruit painters (canvas),
then writes them into app/android/app/src/main/res. Needs: pip install playwright pillow (and a Chrome/Chromium).

    python tools/make_icons.py
"""
import asyncio, base64, io, os, re, shutil, sys
from PIL import Image
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'src', 'game.template.html')
RES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'app', 'android', 'app', 'src', 'main', 'res')
OUT = os.path.join(ROOT, 'tests', 'out', 'icons')
FONT = os.path.join(ROOT, 'src', 'fonts', 'shrikhand-latin-400-normal.woff2')
os.makedirs(OUT, exist_ok=True)
CHROME = os.environ.get('CHROME_PATH') or shutil.which('google-chrome') or shutil.which('chrome') or None

src = open(TPL).read()
def extract(name):
    i = src.index(f'  function {name}(')
    depth, j = 0, src.index('{', i)
    while True:
        c = src[j]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return src[i:j + 1]
        j += 1
painters = '\n'.join(extract(n) for n in ('disc', 'ellipsePath', 'rim', 'shine', 'seedRing', 'paintWatermelonCut', 'paintWatermelon'))
font64 = base64.b64encode(open(FONT, 'rb').read()).decode()

PAGE = """<!doctype html><html><head><style>
@font-face { font-family: Shrikhand; src: url(data:font/woff2;base64,%s) format('woff2'); }
body { margin: 0; background: #000; }
</style></head><body><script>
const TAU = Math.PI * 2;
%s
// sliced watermelon art centred at (0,0), radius r: two halves pushed apart along the cut + a blade streak
function art(g, r) {
  const ang = -0.62, nx = -Math.sin(ang), ny = Math.cos(ang), gap = r * 0.13;
  for (const side of [-1, 1]) {
    g.save();
    g.translate(nx * side * gap, ny * side * gap);
    g.rotate(ang);
    g.beginPath(); if (side > 0) g.rect(-r * 2, 0, r * 4, r * 2); else g.rect(-r * 2, -r * 2, r * 4, r * 2);
    g.clip();
    g.rotate(-ang);
    g.shadowColor = 'rgba(0,0,0,0.35)'; g.shadowBlur = r * 0.12; g.shadowOffsetY = r * 0.05;
    paintWatermelonCut(g, r);
    g.restore();
  }
  // blade streak through the gap
  g.save(); g.rotate(ang);
  const L = r * 1.45;
  const grad = g.createLinearGradient(-L, 0, L, 0);
  grad.addColorStop(0, 'rgba(255,184,31,0)'); grad.addColorStop(0.25, 'rgba(255,184,31,0.85)'); grad.addColorStop(0.75, 'rgba(255,214,120,0.95)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.lineCap = 'round';
  g.strokeStyle = grad; g.lineWidth = r * 0.16; g.beginPath(); g.moveTo(-L, 0); g.lineTo(L, 0); g.stroke();
  g.strokeStyle = 'rgba(255,253,240,0.95)'; g.lineWidth = r * 0.05; g.beginPath(); g.moveTo(-L * 0.8, 0); g.lineTo(L * 0.92, 0); g.stroke();
  g.restore();
}
function plum(g, w, h) {
  const b = g.createRadialGradient(w / 2, h * 0.38, 0, w / 2, h * 0.38, Math.hypot(w, h) * 0.6);
  b.addColorStop(0, '#4a1b4f'); b.addColorStop(0.55, '#2a0f2f'); b.addColorStop(1, '#140616');
  g.fillStyle = b; g.fillRect(0, 0, w, h);
  g.save(); g.globalAlpha = 0.055; g.fillStyle = '#ffb81f';
  g.translate(w / 2, h / 2); g.rotate(-20 * Math.PI / 180);
  const D = Math.hypot(w, h), s = Math.max(w, h) * 0.09;
  for (let x = -D; x < D; x += s * 2) g.fillRect(x, -D, s, D * 2);
  g.restore();
}
function make(w, h, fn) { const c = document.createElement('canvas'); c.width = w; c.height = h; fn(c.getContext('2d'), w, h); return c.toDataURL('image/png'); }
window.render = async (kind, w, h) => {
  await document.fonts.load('80px Shrikhand');
  if (kind === 'legacy' || kind === 'round') return make(w, h, (g) => {
    g.save();
    g.beginPath();
    if (kind === 'round') g.arc(w / 2, h / 2, w / 2, 0, TAU); else g.roundRect(0, 0, w, h, w * 0.2);
    g.clip(); plum(g, w, h); g.translate(w / 2, h / 2); art(g, w * 0.33); g.restore();
  });
  if (kind === 'foreground') return make(w, h, (g) => { g.translate(w / 2, h / 2); art(g, w * 0.235); });   // inside the 66dp safe circle of 108dp
  if (kind === 'splash') return make(w, h, (g) => {
    plum(g, w, h);
    const m = Math.min(w, h), portrait = h > w;
    g.save(); g.translate(w / 2, h * (portrait ? 0.43 : 0.4)); art(g, m * 0.17); g.restore();
    const fs = m * 0.11, ty = h * (portrait ? 0.43 : 0.4) + m * 0.17 * 1.45 + fs * 0.9;
    g.font = fs + 'px Shrikhand'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillStyle = '#1a0b1c'; g.fillText('Fruit Slicer', w / 2, ty + fs * 0.16);
    g.fillStyle = '#ff3d6e'; g.fillText('Fruit Slicer', w / 2, ty + fs * 0.08);
    g.fillStyle = '#ffb81f'; g.fillText('Fruit Slicer', w / 2, ty);
  });
};
</script></body></html>""" % (font64, painters)

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, headless=True)
        page = await br.new_page()
        await page.set_content(PAGE)
        async def get(kind, w, h):
            url = await page.evaluate('([k, w, h]) => render(k, w, h)', [kind, w, h])
            return Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1])))
        # master images at high resolution, scaled down with Lanczos
        legacy = await get('legacy', 1024, 1024); legacy.save(f'{OUT}/icon_legacy_1024.png')
        rnd = await get('round', 1024, 1024)
        fg = await get('foreground', 1024, 1024); fg.save(f'{OUT}/icon_foreground_1024.png')
        for d, s in (('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)):
            legacy.resize((s, s), Image.LANCZOS).save(f'{RES}/mipmap-{d}/ic_launcher.png', optimize=True)
            rnd.resize((s, s), Image.LANCZOS).save(f'{RES}/mipmap-{d}/ic_launcher_round.png', optimize=True)
            f = round(s * 108 / 48)
            fg.resize((f, f), Image.LANCZOS).save(f'{RES}/mipmap-{d}/ic_launcher_foreground.png', optimize=True)
        sizes = {'drawable': (480, 320)}
        for d, (pw, ph) in (('mdpi', (320, 480)), ('hdpi', (480, 800)), ('xhdpi', (720, 1280)), ('xxhdpi', (960, 1600)), ('xxxhdpi', (1280, 1920))):
            sizes[f'drawable-port-{d}'] = (pw, ph); sizes[f'drawable-land-{d}'] = (ph, pw)
        sizes['drawable-land-xxxhdpi'] = (1920, 1280)
        for folder, (w, h) in sizes.items():
            img = await get('splash', w, h)
            img.convert('RGB').save(f'{RES}/{folder}/splash.webp', 'WEBP', quality=88, method=6)
        (await get('splash', 720, 1280)).save(f'{OUT}/splash_preview.png')
        # a preview sheet: square, circle, adaptive (foreground on the background colour, circle mask)
        sheet = Image.new('RGBA', (3 * 300 + 40, 340), (255, 255, 255, 255))
        sheet.paste(legacy.resize((280, 280), Image.LANCZOS), (10, 30), legacy.resize((280, 280), Image.LANCZOS))
        sheet.paste(rnd.resize((280, 280), Image.LANCZOS), (320, 30), rnd.resize((280, 280), Image.LANCZOS))
        ad = Image.new('RGBA', (1024, 1024), (0x2e, 0x12, 0x35, 255)); ad.alpha_composite(fg)
        crop = ad.crop((round(1024 * 18 / 108), round(1024 * 18 / 108), round(1024 * 90 / 108), round(1024 * 90 / 108))).resize((280, 280), Image.LANCZOS)
        mask = Image.new('L', (280, 280), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).ellipse((0, 0, 279, 279), fill=255)
        sheet.paste(crop, (630, 30), mask)
        sheet.save(f'{OUT}/icon_sheet.png')
        await br.close()
    print('icons written to', RES)

asyncio.run(main())
