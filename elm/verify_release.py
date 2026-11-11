"""Verify exact shipped sources against the current release inventory."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent

def inventory(root):
    return {str(p.relative_to(root)).replace('\\','/'):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file() and not ({'.git','__pycache__'} & set(p.relative_to(root).parts)) and p.suffix not in {'.pyc','.pyo'} and p.relative_to(root).as_posix()!='SOURCE_MANIFEST.json'}

def main():
    saved=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text())
    actual=inventory(ROOT)
    expected=saved['files']
    changed=sorted(k for k in actual.keys() & expected.keys() if actual[k]!=expected[k])
    missing=sorted(expected.keys()-actual.keys()); extra=sorted(actual.keys()-expected.keys())
    tree=hashlib.sha256(json.dumps(actual,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    okay=not(changed or missing or extra) and tree==saved['source_tree_sha256']
    print(json.dumps(dict(verified=okay,files=len(actual),source_tree_sha256=tree,changed=changed,missing=missing,unexpected=extra)))
    return 0 if okay else 1

if __name__=='__main__':
    raise SystemExit(main())
