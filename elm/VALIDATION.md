# Validation · 0.2.0-experimental

## Offline, no Hermes needed

```sh
python -B verify_release.py   # file inventory matches SOURCE_MANIFEST.json
python -B demo.py             # synthetic store, retrieval, exact read, read-only refusal
```

## Against an installed Hermes

Use Hermes's own Python and put its source tree on `PYTHONPATH`; set `TMPDIR` to a scratch folder.

```sh
export HERMES_STOCK_SOURCE=/path/to/hermes/source PYTHONPATH=/path/to/hermes/source TMPDIR=/tmp/elm-tests
python -B -m unittest discover -s tests
for f in tests/regression/test_*.py tests/regression/*/test_*.py tests/regression/*/*/test_*.py; do python -B "$f"; done
python -B tests/native_contract.py
python -B tests/native_explicit_contract.py
hermes plugins validate .
```

## Results for this release (2026-11-26, Windows 11, Hermes 0.23.1, Python 3.14)

| Check | Result |
|---|---|
| `hermes plugins validate` | passed; no private-import warnings (0.1.0 had 187) |
| Unit + regression suites | 478 tests, all pass; 22 skipped (optional tokenizer vocabularies not supplied) |
| `native_contract`, `native_explicit_contract` | pass: real Hermes discovery of `plugins/elm-wiki`, `MemoryManager`, `elm_context`/`elm_read`/`elm_status`, background recall |
| Disposable profile | `setup_profile.py new` → `hermes plugins enable elm-wiki` → `memory.provider elm-wiki` → `hermes memory status`: available |
| Other `native_*` harnesses (5) | **not run**: they require a git checkout of Hermes at the old pin `b200f5bc` |

Not established: model tool choice, answer quality, Linux/macOS on this release, measured-budget mode with a
real tokenizer.
