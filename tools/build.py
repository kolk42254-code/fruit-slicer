#!/usr/bin/env python3
"""Build the game: src/game.template.html  ->  index.html (the website and the Android app use this file).

The two OFL fonts in src/fonts are put inside the page as base64, so the page needs no font downloads.
The app version (app/package.json) is written into the page, for the tracking report.
Never edit index.html by hand: edit src/game.template.html, then run:

    python tools/build.py            # writes index.html
    python tools/build.py --check    # only checks that index.html is up to date (exit 1 if not)

It also writes tests/out/www-app/index.html (the Android-app variant, used by the camera tests).
"""
import base64, hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src', 'game.template.html')
FONTS = os.path.join(ROOT, 'src', 'fonts')
FONT_FILES = {
    '__FONT_SHRIKHAND_400__': 'shrikhand-latin-400-normal.woff2',
    '__FONT_BALOO_500__': 'baloo-2-latin-500-normal.woff2',
    '__FONT_BALOO_600__': 'baloo-2-latin-600-normal.woff2',
    '__FONT_BALOO_700__': 'baloo-2-latin-700-normal.woff2',
    '__FONT_BALOO_800__': 'baloo-2-latin-800-normal.woff2',
}
APP_PACKAGE = os.path.join(ROOT, 'app', 'package.json')   # its "version" is shown in the game's tracking report
WEB_TAG = '<meta name="fs-assets" content="cdn">'
APP_TAG = '<meta name="fs-assets" content="local">'


def build_html():
    html = open(SRC, encoding='utf-8').read()
    for key, name in FONT_FILES.items():
        data = open(os.path.join(FONTS, name), 'rb').read()
        if data[:4] != b'wOF2':
            sys.exit(f'{name} is not a woff2 file')
        if html.count(key) != 1:
            sys.exit(f'placeholder {key} found {html.count(key)} times in the template')
        html = html.replace(key, base64.b64encode(data).decode('ascii'))
    version = json.load(open(APP_PACKAGE, encoding='utf-8'))['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        sys.exit(f'app/package.json: unexpected version {version!r}')
    if html.count('__GAME_VERSION__') != 1:
        sys.exit('placeholder __GAME_VERSION__ must be in the template exactly once')
    html = html.replace('__GAME_VERSION__', version)
    left = re.findall(r'__[A-Z0-9_]{6,}__', html)
    if left:
        sys.exit(f'unfilled placeholders: {left}')
    if html.count(WEB_TAG) != 1:
        sys.exit('the template must contain ' + WEB_TAG + ' exactly once')
    return html


def main():
    html = build_html()
    data = html.encode('utf-8')
    out = os.path.join(ROOT, 'index.html')
    if '--check' in sys.argv:
        same = os.path.exists(out) and open(out, 'rb').read() == data
        print('index.html is up to date' if same else 'index.html is OUT OF DATE: run python tools/build.py')
        sys.exit(0 if same else 1)
    open(out, 'wb').write(data)
    print(f'index.html  {len(data):,} bytes  sha256 {hashlib.sha256(data).hexdigest()[:16]}')
    # Android-app variant for local tests (the real app is built by app/scripts/prepare-www.mjs)
    app_dir = os.path.join(ROOT, 'tests', 'out', 'www-app')
    os.makedirs(app_dir, exist_ok=True)
    open(os.path.join(app_dir, 'index.html'), 'wb').write(html.replace(WEB_TAG, APP_TAG).encode('utf-8'))


if __name__ == '__main__':
    main()
