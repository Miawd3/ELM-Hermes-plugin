"""Regenerate stock-plugin/SOURCE_MANIFEST.json from the git index (sha256 of each staged file).

Hashes the committed bytes (LF), not the Windows checkout, so results match on every OS.
Run after `git add`:  python scripts/regen_stock_manifest.py
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = 'stock-plugin'


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout


def main():
    files = [f for f in git('ls-files', '--', PLUGIN).decode().splitlines()
             if f != f'{PLUGIN}/SOURCE_MANIFEST.json' and '__pycache__' not in f]
    manifest = {f[len(PLUGIN) + 1:]: hashlib.sha256(git('show', f':{f}')).hexdigest() for f in sorted(files)}
    path = ROOT / PLUGIN / 'SOURCE_MANIFEST.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
    changed = sorted(k for k in manifest.keys() | old.keys() if manifest.get(k) != old.get(k))
    print(f'{len(manifest)} files; changed: {changed}')


if __name__ == '__main__':
    sys.exit(main())
