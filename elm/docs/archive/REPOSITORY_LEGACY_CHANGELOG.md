# Catalog preparation changes

Base: ea694a0c0a6a8b75b47332f0f92bae2087f10e8f. No upstream repository or live profile was changed.

1. Sanitized 22 personal workstation path occurrences across 11 qualification harnesses. Added portable explicit-prerequisite path helpers and setup documentation.
2. Disabled all plugin update checks, application and installed-ref inspection in the ELM human router. Kept separately requested skill updates and their existing guards. Updated the visible update-panel copy to state that plugin updates are disabled.
3. Made the optional draft command bridge skip foreign recording contexts; owned handler checks and permissions remain intact.
4. Added five focused tests for the changed update/bridge contract.
5. Restored the missing plugin source inventory; regenerated both manifests for these bytes.
6. Retained Apache-2.0 licensing and original notices; copied the same files to repository root.
7. Separated historical preserved-host receipts from fresh tests, documented current-host incompatibility and corrected blanket no-network/model wording.

The optional fail-closed workspace guard is delivered as a separate patch and eight tests, not applied to this baseline. It improves the unsupported-host diagnostic and prevents path/sidebar fallback. It does not restore the removed authoritative ownership API.

Publication presentation: added the three architecture illustrations, a current compatibility warning, exact root-test results, and the test report. Plugin runtime and test source bytes are unchanged from the sanitized preparation bundle.
