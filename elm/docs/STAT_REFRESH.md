# Equal-content source-stat refresh

This isolated follow-on derives from accepted typed policy-v8 tree `68d30cd3cc78714baf4b17a3ebf30a5f9ba999e365eeed5f1d6b364d6c0252c7`. It repairs derived index bookkeeping, not source admission policy. Index policy/schema remains **8**; the separate native memory metadata schema is unchanged.

## Cause and contract

`index_one` reads exact source bytes, hashes them, observes source stats, parses/validates source metadata and typed declarations, validates the document UID, then computes the archive UID projection. On equal content hash and equal projected UID without force, it used to return unchanged without refreshing `documents.mtime_ns` / `size_bytes`. `status_snapshot` correctly checks all three of mtime, size and content hash. Thus an exact-byte restoration or touch could make ordinary sync return exit 0 with `errors: []`, yet keep guarded/native reads unavailable indefinitely.

The equal-content branch now updates **only those two derived stat columns**, only when they differ. It still returns content-unchanged. It preserves the document ID/UID, indexed-at value, sections/internal IDs/public locators, properties, typed labels, links, tags and FTS projection. A subsequent unchanged sync does not update the row. Changed hashes still take the ordinary reindex path even when source size and mtime were restored to their old values.

Validation remains before the fast path. A malformed declaration is not blessed or stat-refreshed. Root/project/identity/source policy, archive UID projection, guarded exact-source freshness and migrations remain unchanged. There is no force-refresh fallback, retry, new cache, blanket reindex, read option or adoption workaround.

## Reproduction and evidence

`tests/test_stat_refresh.py` contains four deterministic regressions: legacy and typed-UID equal-content/stat restoration, changed content with the exact old size/mtime, and malformed typed declarations followed by valid exact-byte restoration. The tests use `os.utime(ns=...)`, not sleep, closed read-only fixture SQLite inspection, and the provider's scrubbed `-B -s -S` engine boundary. Run them through the documented managed validation environment, not an unisolated framework process.

Current source qualification artifacts live outside the source tree in this iteration's `stat-refresh-evidence/`:

- `red-unit/`: meaningful original-v8 failures before the production patch (original test source snapshot retained separately).
- `red-native/`: real stock MemoryManager initially delivers, then refuses before and after ordinary sync on unchanged accepted v8 bytes.
- `green-tight-final/`, `dependent-{typed,provider,source}/`: focused and affected contract checks.
- `green-native/`: fresh native refusal/recovery, exact before/after records and complete native JSON wires, closed read-only SQLite snapshots, same-stat changed-content and malformed-header negative controls. Reads leave canonical/projection bytes and the read-only/explicit-only binding unchanged.
- `SEALED_SOURCE.json`, `full/official/`, final verification/report: hash-bound source and prescribed full qualification. Consult actual receipts; this document makes no prospective pass/count claim.

Run the prescribed `run_validation.py` only after the current manifest is sealed. The parent separately owns independent review, engineering acceptance and any future deployment decision. No live source/profile/canonical store, installed host, benchmark/controller/public data or model/provider was changed or exercised by this repair.
