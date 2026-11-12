# Required host integration

`host.patch` is the complete cumulative experimental patch against official NousResearch/hermes-agent commit `126980e47b826963b26bf57d210106d849322f8a`. It contains actual native host integration, not a standalone plugin or full Hermes distribution.

Apply only to a fresh checkout after `git apply --check`. See [installation](../elm/docs/CANDIDATE_INSTALL.md). Upstream notices/license remain applicable to Hermes and any derived portions. Nothing here claims official adoption or upstream review.

`run-ui-tests.sh` runs the explicitly bounded portable controller subset. Full native testing requires the host runtime and frontend dependencies. See [test report](../TEST_REPORT.md).
