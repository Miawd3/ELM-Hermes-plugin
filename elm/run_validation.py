"""Portable offline regression runner; external pinned Hermes prerequisites only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
EXPECTED_HOST = 'b200f5bc60e31588ba2cb60e288029c4a54ba5fa'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Evidence directory outside plugin source')
    parser.add_argument('--unit-only', action='store_true')
    args = parser.parse_args()
    host = Path(os.environ.get('HERMES_STOCK_SOURCE', '')).resolve()
    if not (host / 'agent/memory_manager.py').is_file():
        parser.error('Set HERMES_STOCK_SOURCE to the dependency-prepared pinned stock checkout')
    head = subprocess.check_output(['git', '-C', str(host), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(host), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    if head != EXPECTED_HOST or dirty:
        parser.error('Host must be unchanged at the documented exact commit')
    out = Path(args.output).resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error('Evidence output must be outside the plugin source')
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HERMES_STOCK_SOURCE=str(host), PYTHONDONTWRITEBYTECODE='1', HERMES_DISABLE_LAZY_INSTALLS='1')
    commands = [('provider_and_setup', ['-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'])]
    for folder in ('tests/regression', 'tests/regression/prior_audit', 'tests/regression/audit', 'tests/regression/audit/reconciliation_safety'):
        for test in sorted((ROOT/folder).glob('test_*.py')):
            commands.append((test.stem, [str(test)]))
    if not args.unit_only:
        commands.extend((p.stem, [str(p)]) for p in sorted((ROOT/'tests').glob('native_*.py')))
        commands.extend((p.stem, [str(p)]) for p in sorted((ROOT/'tests/regression').glob('native_*.py')))
    results=[]
    for name, argv in commands:
        started=time.monotonic()
        try:
            p=subprocess.run([sys.executable, '-B', *argv], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
            stdout,stderr,code=p.stdout,p.stderr,p.returncode
        except subprocess.TimeoutExpired as exc:
            stdout,stderr,code=str(exc.stdout or ''),str(exc.stderr or '')+'\nRunner timeout',124
        (out/f'{name}.stdout').write_text(stdout)
        (out/f'{name}.stderr').write_text(stderr)
        count=re.findall(r'^Ran (\d+) tests? in ',stdout+'\n'+stderr,re.MULTILINE)
        result=dict(name=name,command=[sys.executable,'-B',*argv],exit_code=code,tests=int(count[-1]) if count else None,seconds=round(time.monotonic()-started,3))
        results.append(result)
        print(json.dumps(result),flush=True)
    passed=all(row['exit_code']==0 for row in results)
    source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts}
    report=dict(passed=passed,host_commit=head,host_tracked_clean=not dirty,python=sys.version,unit_test_executions=sum(r['tests'] or 0 for r in results),native_checks=sum(r['name'].startswith('native_') for r in results),results=results,source_sha256=source)
    (out/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
