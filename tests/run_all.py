"""Runs one full test round on the built game and prints a summary.

    python tests/run_all.py r1            # tag names the logs: tests/out/r1_*.log
    python tests/run_all.py r2 --quick    # skips the 4-minute soak

Order: index.html up to date? -> JavaScript syntax -> logic (desktop + phone) -> camera -> errors -> soak.
The project rule: run two full rounds on the final files before publishing (and the CI emulator test).
"""
import os, re, subprocess, sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
OUT = os.path.join(TESTS, 'out')
tag = next((a for a in sys.argv[1:] if not a.startswith('--')), 'r1')
quick = '--quick' in sys.argv
os.makedirs(OUT, exist_ok=True)


def run(cmd, log):
    with open(os.path.join(OUT, log), 'w') as f:
        return subprocess.run(cmd, cwd=TESTS, stdout=f, stderr=subprocess.STDOUT).returncode


steps = [('build check', [sys.executable, os.path.join(ROOT, 'tools', 'build.py'), '--check'], f'{tag}_build.log'),
         ('JavaScript syntax', [sys.executable, os.path.join(TESTS, 'check_js.py')], f'{tag}_js.log'),
         ('logic', [sys.executable, 't2_logic.py', tag], f'{tag}_logic.log'),
         ('camera', [sys.executable, 't2_camera.py', tag], f'{tag}_camera.log'),
         ('errors', [sys.executable, 't2_errors.py', tag], f'{tag}_errors.log')]
if not quick:
    steps.append(('soak', [sys.executable, 't2_soak.py', '4', tag], f'{tag}_soak.log'))

failed = 0
for name, cmd, log in steps:
    rc = run(cmd, log)
    text = open(os.path.join(OUT, log)).read()
    summary = re.findall(r'^== .*$', text, re.M)
    print(f'{name:18s} exit {rc}  {summary[-1] if summary else text.strip().splitlines()[-1] if text.strip() else ""}')
    for line in re.findall(r'^FAIL .*$', text, re.M):
        print('   ', line[:300])
    failed += rc != 0
print('ROUND', tag, 'PASSED' if not failed else f'FAILED ({failed} step(s))')
sys.exit(1 if failed else 0)
