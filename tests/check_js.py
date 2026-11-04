"""Syntax-checks the game's JavaScript (the inline <script> in index.html) with `node --check`."""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
page = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'index.html')
scripts = re.findall(r'<script>(.*?)</script>', open(page, encoding='utf-8').read(), re.S)
if len(scripts) != 1:
    sys.exit(f'expected 1 inline script, found {len(scripts)}')
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(scripts[0])
rc = subprocess.run(['node', '--check', f.name]).returncode
os.unlink(f.name)
print('JavaScript syntax OK' if rc == 0 else 'JavaScript syntax ERROR')
sys.exit(rc)
