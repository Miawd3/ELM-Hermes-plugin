# Experimental private-chat record lane

Requires matching recovery host APIs. In-process only; no hosted arbitrary record callback or
model-tool/provider injection. Legacy workspace source remains unadopted and unqualified.

RPCs:
- `private.status`: read metadata for authenticated current private chat.
- `private.setup` with `confirm:true`: fresh per-principal store only. Existing/partial roots refuse.
- `private.create` with title,text,sources: creates pending current-chat record. Optional evidence
  labels/sensitive flag; no caller scope/root/principal/project, approval, grant or dependency override.
- `private.approve` with record_id,expected_revision,confirm:true: exact pending current-chat record.
- `private.recall` with optional limit1..20: approved eligible current-chat records only, sources
  preserved and explicitly unverified, returned as untrusted memory data. No similarity ranking yet.

Record storage is separate from legacy scopes, bound by a principal-qualified namespace and
immutable owner/store marker. Recall does not create files/scopes. Sensitive records and inferred
user information stay withheld even after approval. Chat metadata revision reveals only that chat's
record changes, not another chat's writes.

Bounded prototype:512 records per principal store,4MiB exact serialized store,8KiB record text,
one-to-eight bounded sources,32KiB recall result. Limits return errors before an over-limit write;
large existing files fail closed. No million-record scaling or retrieval benchmark claim.

Native host read gate requires read capability and current canonical owner. If a project is selected,
its current catalog eligibility is checked too, but project records are NEVER read. Clear an obsolete
binding before private reads when its selected project is archived/deleted. Results are materialized
inside the fence and withheld on invalidation. Locks stabilize native authority but do not sandbox
hostile local filesystem processes or make external writes exactly-once.

No deletion/correction endpoints, migration, shared-project consent, automatic capture or provider
recall yet. Data persistence/cleanup remains manual until reviewed lifecycle operations are added.
Do not deploy this prototype as a complete privacy lifecycle or finished ELM replacement.
