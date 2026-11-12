# Portable ELM UI/controller checks

Run `bash integration/run-ui-tests.sh` from the repository root. Requires Node.js with the built-in test runner. The first group contains 159 tests; the second runs five dependency-free message-presentation tests.

These tests load the actual shipped plugin source with synthetic SDK/React bindings. They establish controller state, scoping, lifecycle and parser behavior, not an installed Hermes UI acceptance test.

The real-React settings test remains in `message-presentation.test.mjs`, but is explicitly excluded by the runner's name filter because the standalone repository does not contain Hermes React dependencies. To run that test, set `HERMES_SOURCE_CHECKOUT` to the qualified host with its frontend dependencies installed and run the file without the filter.

Native folder, importance and rich-contract review suites require a separately reconstructed patched host. They are outside this dependency-free subset. The complete recovery suite's initial rerun recorded 164 passes and four missing-environment failures; it was not a full-suite pass.
