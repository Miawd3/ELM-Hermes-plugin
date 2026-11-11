# Optional host/browser qualification prerequisites

The source export removes personal workstation paths from the retained test harnesses. It does not bundle Hermes, browser binaries, JavaScript dependencies, or the earlier frozen UI suites. This path-only adaptation does not transfer prior host/browser qualification to this export.

Provide these explicit environment variables for the corresponding optional lanes:

- HERMES_STOCK_SOURCE: dependency-prepared Hermes source checkout. The historical run_validation.py additionally requires its documented exact commit.
- ELM_TEST_DEPS: Python site-packages directory for that prepared Hermes runtime, used by browser backend fixtures.
- ELM_TEST_PYTHON: absolute Python executable for browser fixtures; defaults to python3 (python on Windows).
- ELM_TEST_BROWSER: absolute Chromium-compatible browser executable for browser fixtures.
- ELM_LEGACY_UI_TESTS: separate frozen legacy UI test directory, required only by important_memory_regression.mjs; it is not included here.
- ELM_TEST_SCRATCH_ROOT: optional absolute disposable test-work directory; defaults to the OS temporary directory under elm-source-qualification.

Use a new label for each browser run. The scripts preserve their existing synthetic owner markers, refusal behavior, model-transport fixtures and assertions. Their SDK fixture imports use the test bundler's existing @ alias to the explicitly selected Hermes source.

Do not point these variables at a live user profile or canonical memory store. Missing prerequisites are blockers, not passing tests. Browser fixtures bind only to localhost and block non-fixture browser requests.
