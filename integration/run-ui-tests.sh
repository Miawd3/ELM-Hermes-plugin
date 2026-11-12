#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
suites=()
for file in integration/ui-tests/*.test.mjs; do
  [[ "$file" == */message-presentation.test.mjs ]] && continue
  suites+=("$file")
done
node --test "${suites[@]}"
# Explicitly select the five dependency-free cases; keep the React SSR test in source.
node --test --test-name-pattern='finite explicit|fences, bounded|default off|enable, settings|unsupported native' integration/ui-tests/message-presentation.test.mjs
