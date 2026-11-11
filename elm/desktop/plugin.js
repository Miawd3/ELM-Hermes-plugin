import * as SDK from "@hermes/plugin-sdk";
import {
  createElement as h,
  useId,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
} from "react";

const value = (atom) => atom?.get?.();
function validRecord(r) {
  return (
    r &&
    ["id", "scope_id", "title", "text", "topic"].every(
      (key) => typeof r[key] === "string",
    ) &&
    Number.isSafeInteger(r.revision) && r.revision > 0 &&
    ["user", "work", "reference"].includes(r.domain) &&
    [
      "explicit_fact",
      "preference",
      "observation",
      "interpretation",
      "summary",
      "procedure",
      "reference",
    ].includes(r.kind) &&
    [
      "explicit_statement",
      "direct_observation",
      "source_document",
      "inference",
    ].includes(r.basis) &&
    ["pending", "approved", "invalidated"].includes(r.state) &&
    Array.isArray(r.dependencies) &&
    r.dependencies.every((pin) => pin && typeof pin === "object" && !Array.isArray(pin) &&
      Object.keys(pin).length === 2 && typeof pin.id === "string" && pin.id.length > 0 &&
      Number.isSafeInteger(pin.revision) && pin.revision > 0) &&
    new Set(r.dependencies.map((pin) => pin.id)).size === r.dependencies.length &&
    Array.isArray(r.sources) &&
    r.sources.length > 0 &&
    r.sources.every(
      (s) =>
        s &&
        typeof s.ref === "string" &&
        s.ref.length > 0 &&
        (s.quote == null || typeof s.quote === "string") &&
        (s.sha256 == null || typeof s.sha256 === "string"),
    )
  );
}

// Receipt comparison is deliberately separate from HTTP/overview availability.
const same = (a, b) => {
  if (Object.is(a, b)) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length &&
    keys.every((key) => Object.hasOwn(b, key) && same(a[key], b[key]));
};
const contains = (actual, expected) => actual && expected &&
  Object.keys(expected).every((key) => same(actual[key], expected[key]));
const sameIds = (a, b) => Array.isArray(a) && Array.isArray(b) &&
  a.every((id) => typeof id === "string") &&
  new Set(a).size === a.length && same([...a].sort(), [...b].sort());
const validGrant = (g) => g &&
  ["source_scope", "target_scope", "record_id"].every((k) => typeof g[k] === "string" && g[k]) &&
  Number.isInteger(g.record_revision) && g.record_revision > 0;
function draftTypeMatches(result, requestedKind) {
  const storedKind = requestedKind === "observation" ? "interpretation" : requestedKind;
  if (!["summary", "observation", "procedure"].includes(requestedKind) ||
      result.kind !== storedKind || result.basis !== "inference") return false;
  const receipt = result.generation_receipt;
  if (!receipt) return requestedKind !== "observation";
  return receipt.schema === 1 && receipt.requested_kind === requestedKind &&
    receipt.stored_kind === storedKind && receipt.basis === result.basis &&
    receipt.record_id === result.id && receipt.record_revision === result.revision;
}
function confirmEffect(path, method, body, result, before, after, record) {
  if (!result || typeof result !== "object") return "The write result metadata is missing.";

  if (path === "/record" || path === "/draft" ||
      (record && (method === "PATCH" || path.endsWith("/approve")))) {
    if (!validRecord(result) || result.revision < 1)
      return "The full returned record identity, revision or state is missing.";
    const expected = path === "/record" ? body : method === "PATCH" ? body.changes : {};
    if (!contains(result, expected) || result.scope_id !== before.selected_scope_id ||
        (record && (result.id !== record.id || result.revision <= record.revision)) ||
        (!record && before.records.some((r) => r.id === result.id)) ||
        (path.endsWith("/approve") && result.state !== "approved") ||
        (path === "/draft" && (!draftTypeMatches(result, body.kind) || result.state !== "pending" ||
          !sameIds(result.dependencies.map((pin) => pin.id), body.record_ids) ||
          result.dependencies.some((pin) => pin.revision !== before.records.find((r) => r.id === pin.id)?.revision))))
      return "The returned record contradicts the requested change.";
    const observed = after.records.find((r) => r.id === result.id);
    const fields = ["id", "revision", "scope_id", "title", "text", "domain", "kind", "basis", "topic", "sources", "state", "dependencies", "sensitive", "created_at", "updated_at"];
    if (!observed || fields.some((k) => Object.hasOwn(result, k) && !same(result[k], observed[k])))
      return "The exact returned record was not found in the fresh overview.";
    return "";
  }
  if (path.endsWith("/delete") && record) {
    if (!Array.isArray(result.deleted_ids) || !result.deleted_ids.includes(record.id) ||
        !result.deleted_ids.every((id) => typeof id === "string"))
      return "The deleted record identifiers are missing or contradictory.";
    return after.records.some((r) => result.deleted_ids.includes(r.id)) ||
      after.grants?.some((g) => result.deleted_ids.includes(g.record_id))
      ? "A deleted record or its active share is still present in the fresh overview." : "";
  }
  if (path === "/grants") {
    if (result.source_scope !== body.source_scope || result.target_scope !== body.target_scope ||
        !sameIds(result.record_ids, body.record_ids) || !Number.isInteger(result.revision) ||
        !Number.isInteger(after.revision) || after.revision < result.revision)
      return "The sharing receipt does not identify the requested records and areas.";
    if (!Array.isArray(after.grants))
      return "Active grants are not listed by this API; sharing cannot be independently confirmed.";
    const matches = (id) => after.grants.filter((g) => g.source_scope === body.source_scope &&
      g.target_scope === body.target_scope && g.record_id === id);
    return body.record_ids.every((id) => method === "DELETE"
      ? matches(id).length === 0
      : matches(id).length === 1 && matches(id)[0].record_revision ===
        before.records.find((r) => r.id === id)?.revision)
      ? "" : "The active grant inventory contradicts the requested sharing change.";
  }
  if (path === "/learning")
    return typeof result.learning_enabled === "boolean" && result.learning_enabled === body.enabled &&
      after.status?.learning_enabled === result.learning_enabled
      ? "" : "Draft-generation settings are missing or do not match the requested value.";
  if (path === "/scopes/privacy") {
    const observed = after.scopes.find((s) => s.id === body.scope_id);
    return result.id === body.scope_id && result.private === body.private &&
      ["id", "kind", "label", "private"].every((k) => Object.hasOwn(result, k) && same(result[k], observed?.[k]))
      ? "" : "The returned area privacy does not match the requested value and fresh overview.";
  }
  if (path === "/setup")
    return result.initialized === true && after.setup === true
      ? "" : "Fresh-store initialization was not confirmed by its result and overview.";
  if (path === "/index/rebuild")
    return body.scope_id === before.selected_scope_id && result.scope_id === body.scope_id &&
      after.selected_scope_id === body.scope_id && after.status?.scope_id === body.scope_id &&
      result.generation != null && after.status?.generation === result.generation &&
      result.index_state === "ready" && after.status?.index_state === "ready"
      ? "" : "The index generation and ready state cannot be independently confirmed.";
  return "This operation has no exact readback contract.";
}
function cleanupWarning(result) {
  const cleanup = result?.index_cleanup;
  const held = cleanup?.held_paths;
  const incomplete = cleanup?.complete === false || (Array.isArray(held) && held.length > 0);
  return [typeof result?.warning === "string" ? result.warning : "",
    incomplete ? `Derived-index cleanup is incomplete${Array.isArray(held) && held.length ? `; held paths: ${held.join(", ")}` : ""}. The record change may already be committed; do not repeat the mutation to retry cleanup.` : ""]
    .filter(Boolean).join(" ");
}

// ctx.rest is ambient-only on this SDK: it accepts no profile or connection pin.
// Never substitute requestProfile (RPC) for the authenticated plugin REST door.
export function createMemoryController(ctx, host = SDK.host) {
  let disposed = false,
    generation = 0,
    selection = "",
    identityKey = "";
  let snapshot = {
    data: null,
    phase: "idle",
    error: "",
    notice: "",
    pending: false,
    unconfirmed: false,
    generation: 0,
  };
  const listeners = new Set();
  const publish = (change) => {
    snapshot = { ...snapshot, ...change };
    for (const fn of listeners) fn();
  };
  function identity() {
    const s = host?.state || {};
    const session = value(s.focusedStoredSessionId);
    const profile = value(s.focusedSessionProfile);
    const owner = value(s.focusedSessionOwner);
    const connection = value(s.connectionId);
    const ambient = value(s.profile);
    const gateway = value(s.gateway);
    const epoch =
      typeof SDK.gatewayActivationEpoch === "function"
        ? SDK.gatewayActivationEpoch()
        : null;
    const key = JSON.stringify([
      session,
      profile,
      owner,
      connection,
      ambient,
      gateway,
      epoch,
    ]);
    let error = "";
    if (!session) error = "Focus a saved chat to inspect its memory boundary.";
    else if (!owner?.connectionId || !profile || !connection || !ambient)
      error =
        "The focused chat owner is unavailable. Update Hermes Desktop or resolve the chat owner.";
    else if (
      owner.profile !== profile ||
      profile !== ambient ||
      owner.connectionId !== connection
    )
      error =
        "This chat belongs to another profile or connection. Plugin REST cannot safely route there; select its owning gateway first.";
    else if (gateway !== "open")
      error = "The gateway is unavailable. Reconnect, then refresh memory.";
    return { session, key, error };
  }
  function sync() {
    const current = identity();
    if (current.key !== identityKey) {
      identityKey = current.key;
      generation++;
      selection = "";
      publish({
        data: null,
        phase: current.error ? "unavailable" : "idle",
        error: current.error,
        notice: "",
        pending: false,
        stale: false,
        unconfirmed: false,
        ownerKey: identityKey,
        generation,
      });
    }
    return current;
  }
  async function refresh(scope = selection, retainSameArea = true, requireSetup = false) {
    const current = sync();
    if (disposed || current.error) return false;
    const retained =
      retainSameArea &&
      snapshot.data?.setup &&
      (!scope || scope === snapshot.data.selected_scope_id)
        ? snapshot.data
        : null;
    selection = scope || "";
    const token = ++generation,
      key = current.key;
    publish({
      data: retained,
      stale: Boolean(retained),
      phase: retained ? "refreshing" : "loading",
      error: "",
      notice: "",
      generation,
    });
    try {
      const query = new URLSearchParams({ session_id: current.session });
      if (selection) query.set("scope_id", selection);
      const data = await ctx.rest(`/overview?${query}`, { timeoutMs: 20000 });
      if (disposed || token !== generation || identity().key !== key)
        return false;
      if (
        data?.schema !== 1 ||
        typeof data.setup !== "boolean" ||
        (requireSetup && data.setup !== true) ||
        !Array.isArray(data.scopes) ||
        !Array.isArray(data.records) ||
        data.context?.session_id !== current.session ||
        (selection && data.selected_scope_id !== selection)
      )
        throw new Error(
          "Memory overview is unavailable or has an incompatible scope/schema. Nothing from another chat was loaded.",
        );
      if (
        !data.scopes.every(
          (s) =>
            s &&
            typeof s.id === "string" &&
            typeof s.label === "string" &&
            ["personal", "workspace", "chat"].includes(s.kind) &&
            typeof s.private === "boolean",
        ) ||
        !data.records.every(validRecord) ||
        (data.grants !== undefined && (!Array.isArray(data.grants) || !data.grants.every(validGrant)))
      )
        throw new Error(
          "Memory returned malformed areas or records. Refresh after the backend is corrected.",
        );
      if (
        data.setup &&
        !data.scopes.some((s) => s.id === data.selected_scope_id)
      )
        throw new Error("The selected memory area is unavailable.");
      publish({
        data,
        stale: false,
        phase: data.setup ? "ready" : "unconfigured",
        unconfirmed: false,
        error: "",
      });
      return true;
    } catch (e) {
      if (!disposed && token === generation && identity().key === key)
        publish({
          data: retained,
          stale: Boolean(retained),
          phase: "error",
          error: e?.message || "Memory could not be loaded.",
        });
      return false;
    }
  }
  function creationContext() {
    sync();
    return { ownerKey: identityKey, generation, scope_id: snapshot.data?.selected_scope_id };
  }
  async function createRecord(changes, destination, pin) {
    sync();
    const data = snapshot.data;
    const chat = privateCreationScope(data);
    if (!pin || pin.ownerKey !== identityKey || pin.generation !== generation ||
        pin.scope_id !== data?.selected_scope_id ||
        !["current-area", "private-chat"].includes(destination) ||
        (destination === "private-chat" && !chat)) {
      publish({ error: "The creation destination is stale or the current chat is not private. Refresh and review before saving.", notice: "" });
      return false;
    }
    const scope_id = destination === "private-chat" ? chat.id : data.selected_scope_id;
    return action("/record", "POST", { ...changes, scope_id, state: "pending" }, "Saved", { pin, scope_id });
  }
  async function action(path, method, body, label = "Saved", creation = null) {
    const current = sync();
    if (
      disposed ||
      current.error ||
      snapshot.pending ||
      !snapshot.data ||
      snapshot.unconfirmed ||
      !["ready", "unconfigured"].includes(snapshot.phase)
    )
      return false;
    const before = snapshot.data;
    const selected = before.selected_scope_id;
    const recordMatch = path.match(/^\/records\/([^/]+)/);
    const record = recordMatch
      ? snapshot.data.records.find(
          (r) => r.id === decodeURIComponent(recordMatch[1]),
        )
      : null;
    if (
      (body.scope_id && body.scope_id !== selected && !(path === "/record" && method === "POST" &&
        creation?.scope_id === body.scope_id && creation.pin.ownerKey === current.key &&
        creation.pin.generation === generation && creation.pin.scope_id === selected &&
        privateCreationScope(before)?.id === body.scope_id)) ||
      (body.source_scope && body.source_scope !== selected) ||
      (recordMatch &&
        (!record ||
          (body.expected_revision != null &&
            record.revision !== body.expected_revision)))
    ) {
      publish({
        error:
          "The memory area changed or this record is stale. Refresh and review before saving.",
        notice: "",
      });
      return false;
    }
    const token = generation,
      key = current.key;
    publish({ pending: true, error: "", notice: "Saving…" });
    try {
      const receipt = await ctx.rest(path, { method, body, timeoutMs: 60000 });
      if (disposed || token !== generation || identity().key !== key)
        return false;
      if (receipt?.ok !== true)
        throw new Error(receipt?.message || "The write was not acknowledged.");
      const verificationGeneration = generation + 1;
      const refreshed = await refresh(selection, !path.endsWith("/delete"), true);
      if (
        disposed ||
        generation !== verificationGeneration ||
        identity().key !== key
      )
        return false;
      let observed = snapshot.data;
      if (refreshed && creation && body.scope_id !== selected) {
        const query = new URLSearchParams({ session_id: current.session, scope_id: body.scope_id });
        try {
          observed = await ctx.rest(`/overview?${query}`, { timeoutMs: 20000 });
          if (observed?.schema !== 1 || observed.setup !== true ||
              observed.context?.session_id !== current.session || observed.selected_scope_id !== body.scope_id ||
              privateCreationScope(observed)?.id !== body.scope_id ||
              !Array.isArray(observed.records) || !observed.records.every(validRecord)) observed = null;
        } catch { observed = null; }
        if (disposed || generation !== verificationGeneration || identity().key !== key) return false;
      }
      const reason = refreshed && observed
        ? confirmEffect(path, method, body, receipt.result,
            creation ? { ...before, selected_scope_id: body.scope_id } : before, observed, record)
        : "The fresh overview could not be verified.";
      const verified = !reason;
      const warning = cleanupWarning(receipt.result);
      publish({
        pending: false,
        unconfirmed: !verified,
        notice: [verified
          ? warning ? `${label}: record/settings effect verified in memory; cleanup is not fully verified.`
            : `${label} and verified in memory.`
          : `Write acknowledged; effect unconfirmed. ${reason} Your draft is retained. Refresh to reconcile before trying again; nothing is retried automatically.`,
          warning].filter(Boolean).join(" "),
      });
      return verified;
    } catch (e) {
      if (!disposed && token === generation && identity().key === key)
        publish({
          pending: false,
          error: e?.message || "The write failed. Your draft is still here.",
          notice:
            "Save failed or is unconfirmed. Your draft is unchanged. Refresh to reconcile a timeout before retrying; nothing is retried automatically.",
        });
      return false;
    }
  }
  async function deletionPreview(record) {
    const current = sync();
    if (
      disposed ||
      current.error ||
      snapshot.pending ||
      snapshot.phase !== "ready"
    )
      return null;
    const token = generation,
      key = current.key;
    publish({ pending: true, error: "", notice: "Loading deletion preview…" });
    try {
      const receipt = await ctx.rest(
        `/records/${encodeURIComponent(record.id)}/delete-preview`,
        { method: "POST", body: {}, timeoutMs: 20000 },
      );
      if (disposed || token !== generation || identity().key !== key)
        return null;
      const preview = receipt?.result;
      if (
        !receipt.ok ||
        preview?.record_id !== record.id ||
        !Number.isSafeInteger(preview.revision) ||
        preview.revision !== snapshot.data?.revision ||
        !preview.preview_token ||
        !Array.isArray(preview.dependent_ids)
      )
        throw new Error(
          "The deletion preview is stale or invalid. Refresh before deleting.",
        );
      publish({
        pending: false,
        notice: "Review the deletion below. Nothing has been deleted.",
      });
      return preview;
    } catch (e) {
      if (!disposed && token === generation && identity().key === key)
        publish({
          pending: false,
          error: e?.message || "Deletion preview failed.",
          notice: "",
        });
      return null;
    }
  }
  function reconcile() {
    const old = identityKey;
    sync();
    if (identityKey !== old) void refresh();
  }
  const state = host?.state || {};
  const unlisten = [
    "focusedStoredSessionId",
    "focusedSessionProfile",
    "focusedSessionOwner",
    "profile",
    "connectionId",
    "gateway",
  ]
    .map((key) => state[key])
    .filter((a) => typeof a?.listen === "function")
    .map((a) => a.listen(reconcile));
  sync();
  return {
    getSnapshot: () => snapshot,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    refresh,
    // Only createRecord may supply the internal cross-area creation pin.
    action: (path, method, body, label) => action(path, method, body, label),
    creationContext,
    createRecord,
    deletionPreview,
    reconcile,
    dispose() {
      disposed = true;
      generation++;
      for (const fn of unlisten) fn();
      listeners.clear();
    },
  };
}

const row = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "0.6rem",
};
const section = { display: "grid", gap: "0.8rem", marginBlock: "1.5rem" };
const muted = { color: "var(--ui-text-secondary)" };
const plain = (text) => String(text ?? "").replaceAll("_", " ");
const Button = SDK.Button || "button";
const Input = SDK.Input || "input";
const Textarea = SDK.Textarea || "textarea";
const button = (text, onClick, disabled = false, extra = {}) =>
  h(
    Button,
    {
      type: "button",
      variant: "secondary",
      size: "sm",
      disabled,
      onClick,
      style: { justifySelf: "start", maxWidth: "100%", whiteSpace: "normal" },
      ...extra,
    },
    text,
  );
function Field({ label, children }) {
  const id = useId();
  return h(
    "div",
    { style: { display: "grid", gap: "0.35rem", minWidth: 0 } },
    h("label", { htmlFor: id }, label),
    children(id),
  );
}
function TextField({ label, value, onChange, multiline = false, ...props }) {
  return h(Field, { label }, (id) =>
    h(multiline ? Textarea : Input, {
      id,
      "aria-label": label,
      value,
      onChange: (e) => onChange(e.target.value),
      ...props,
    }),
  );
}
function Choice({ label, value, options, onChange, disabled = false }) {
  return h(Field, { label }, (id) =>
    h(
      "select",
      {
        id,
        "aria-label": label,
        value,
        disabled,
        onChange: (e) => onChange(e.target.value),
        style: {
          font: "inherit",
          color: "var(--ui-text-primary)",
          background: "var(--ui-bg-secondary)",
          border: "1px solid var(--ui-stroke-secondary)",
          padding: "0.35rem",
          maxWidth: "100%",
        },
      },
      options.map((o) =>
        h(
          "option",
          { key: o.value ?? o, value: o.value ?? o },
          o.label ?? plain(o),
        ),
      ),
    ),
  );
}
const domains = ["user", "work", "reference"];
const kinds = [
  "explicit_fact",
  "preference",
  "observation",
  "interpretation",
  "summary",
  "procedure",
  "reference",
];
const bases = [
  "explicit_statement",
  "direct_observation",
  "source_document",
  "inference",
];
function privateCreationScope(data) {
  if (data?.context?.private !== true || !Array.isArray(data.scopes)) return null;
  const matches = data.scopes.filter((s) => s.id === data.context.chat_scope_id && s.kind === "chat" && s.private === true);
  return matches.length === 1 ? matches[0] : null;
}
function RecordForm({ record, scope, data, controller, pending, onClose }) {
  const [creationPin] = useState(() => controller.creationContext());
  const [destination, setDestination] = useState("current-area");
  const privateChat = privateCreationScope(data);
  const target = destination === "private-chat" ? privateChat : scope;
  const [draft, setDraft] = useState(() => ({
    title: record?.title || "",
    text: record?.text || "",
    domain: record?.domain || (scope.kind === "personal" ? "user" : "work"),
    kind: record?.kind || "explicit_fact",
    basis: record?.basis || "explicit_statement",
    topic: record?.topic || "facts",
    ref: "",
    quote: "",
    sources: record?.sources || [],
  }));
  const [error, setError] = useState("");
  const set = (key) => (next) => setDraft((d) => ({ ...d, [key]: next }));
  async function submit(e) {
    e.preventDefault();
    const sources = [
      ...draft.sources,
      ...(draft.ref.trim()
        ? [{ ref: draft.ref, ...(draft.quote ? { quote: draft.quote } : {}) }]
        : []),
    ];
    if (!draft.title.trim() || !draft.text.trim() || !sources.length) {
      setError(
        "Add a title, record text, and at least one exact source reference.",
      );
      return;
    }
    setError("");
    const changes = {
      title: draft.title,
      text: draft.text,
      domain: draft.domain,
      kind: draft.kind,
      basis: draft.basis,
      topic: draft.topic,
      sources,
    };
    const ok = record
      ? await controller.action(
          `/records/${encodeURIComponent(record.id)}`,
          "PATCH",
          { expected_revision: record.revision, changes },
        )
      : await controller.createRecord(changes, destination, creationPin);
    if (ok) onClose();
    else {
      const state = controller.getSnapshot();
      setError(
        `${state.error || state.notice || "Save could not be confirmed."} Your entered draft is retained.`,
      );
    }
  }
  return h(
    "form",
    {
      onSubmit: submit,
      style: section,
      "aria-label": record ? "Correct record" : "Add record",
    },
    h("h3", null, record ? "Correct this record" : "Add a new record"),
    h(
      "p",
      { style: muted },
      record
        ? "A correction to an approved record stays approved. Dependent drafts may become invalidated."
        : "Visibility follows the destination below. Approval is separate: new records start pending, not approved for recall. Saving changes no area privacy and grants no sharing or recall access.",
    ),
    h(
      "fieldset",
      {
        disabled: pending,
        style: {
          display: "grid",
          gap: "0.75rem",
          minWidth: 0,
          border: 0,
          padding: 0,
          margin: 0,
        },
      },
      !record && h(Choice, {
        label: "New record destination",
        value: destination,
        onChange: setDestination,
        options: [
          { value: "current-area", label: `Current area: ${scope.label} · ${scope.private ? "Private" : "Scoped"} (${scope.id})` },
          ...(privateChat && privateChat.id !== scope.id ? [{ value: "private-chat", label: `Current private chat: ${privateChat.label} (${privateChat.id})` }] : []),
        ],
      }),
      !record && h("p", { style: muted }, target
        ? `Destination: ${target.label} (${target.id}) · ${target.private ? "Private" : "Scoped"}. Private is a recall boundary, not encryption.`
        : "The private-chat destination is unavailable. Choose the current area or refresh and review."),
      h(TextField, {
        label: "Title",
        value: draft.title,
        onChange: set("title"),
        maxLength: 300,
        required: true,
      }),
      h(TextField, {
        label: "Record text",
        value: draft.text,
        onChange: set("text"),
        multiline: true,
        rows: 4,
        required: true,
        spellCheck: true,
      }),
      h(
        "div",
        { style: row },
        h(Choice, {
          label: "Domain",
          value: draft.domain,
          options: domains,
          onChange: set("domain"),
        }),
        h(Choice, {
          label: "Record kind",
          value: draft.kind,
          options: kinds,
          onChange: set("kind"),
        }),
        h(Choice, {
          label: "Evidence basis",
          value: draft.basis,
          options: bases,
          onChange: set("basis"),
        }),
      ),
      h(TextField, {
        label: "Topic",
        value: draft.topic,
        onChange: set("topic"),
        required: true,
      }),
      draft.sources.length > 0 &&
        h(
          "div",
          { style: { display: "grid", gap: "0.75rem" } },
          h(
            "p",
            { style: muted },
            "Existing exact sources are retained unless you remove them. Add a replacement below if a source was wrong.",
          ),
          draft.sources.map((source, index) =>
            h(
              "div",
              { key: index, style: row },
              h("code", { style: { overflowWrap: "anywhere" } }, source.ref),
              button(
                `Remove source ${index + 1}`,
                () =>
                  setDraft((d) => ({
                    ...d,
                    sources: d.sources.filter((_, i) => i !== index),
                  })),
                pending,
              ),
            ),
          ),
        ),
      h(TextField, {
        label: "Exact source reference",
        value: draft.ref,
        onChange: set("ref"),
        placeholder: "A document section or saved message reference",
      }),
      h(TextField, {
        label: "Exact quote (optional)",
        value: draft.quote,
        onChange: set("quote"),
        multiline: true,
        rows: 2,
      }),
      error && h("p", { role: "alert" }, error),
      h(
        "div",
        { style: row },
        h(
          Button,
          { type: "submit", size: "sm", disabled: pending },
          record ? "Save correction" : "Save pending record",
        ),
        button("Cancel", onClose, pending),
      ),
    ),
  );
}
export function isCommunicationCard(record) {
  return (
    record.state === "approved" &&
    record.sensitive === false &&
    record.domain === "user" &&
    record.kind === "preference" &&
    record.topic === "communication" &&
    record.basis === "explicit_statement"
  );
}
export function shareTargets(record, source, scopes) {
  if (
    record.state !== "approved" ||
    (source.kind !== "personal" && source.private) ||
    (source.kind === "personal" && !isCommunicationCard(record))
  )
    return [];
  return scopes.filter(
    (target) =>
      target.id !== source.id &&
      (!target.private || isCommunicationCard(record)),
  );
}
function Sharing({ record, scope, scopes, grants, controller, pending }) {
  const [target, setTarget] = useState("");
  const targets = shareTargets(record, scope, scopes);
  const payload = {
    source_scope: scope.id,
    target_scope: target,
    record_ids: [record.id],
  };
  return h(
    "section",
    { style: section, "aria-label": "Record sharing" },
    h("h4", null, "Share this one record"),
    h(
      "p",
      null,
      "No automatic sharing. Private source containers cannot export records. Only individually approved, non-sensitive communication preferences can enter a private target or leave Personal.",
    ),
    h(
      "p",
      { style: muted },
      Array.isArray(grants)
        ? "See Current sharing for the active grant inventory. This inspector metadata does not authorize model recall."
        : "The API does not list active grants here. A request is acknowledged by the server; this view cannot independently enumerate sharing.",
    ),
    h(Choice, {
      label: "Sharing target",
      value: target,
      onChange: setTarget,
      disabled: pending,
      options: [
        { value: "", label: "Choose a memory area" },
        ...scopes
          .filter((t) => t.id !== scope.id)
          .map((t) => ({
            value: t.id,
            label: `${t.label}${t.private ? " · Private" : ""}${targets.some((eligible) => eligible.id === t.id) ? "" : " · Revoke only"}`,
          })),
      ],
    }),
    !targets.length &&
      h("p", null, "This record has no eligible sharing targets."),
    h(
      "div",
      { style: row },
      button(
        "Share this record",
        () =>
          void controller.action(
            "/grants",
            "POST",
            payload,
            "Sharing request acknowledged",
          ),
        pending || !targets.some((t) => t.id === target),
      ),
      button(
        "Revoke sharing",
        () =>
          void controller.action(
            "/grants",
            "DELETE",
            payload,
            "Revocation request acknowledged",
          ),
        pending || !target,
      ),
    ),
  );
}
function RecordView({ record, scope, scopes, grants, controller, pending, onEdit }) {
  const [preview, setPreview] = useState(null);
  const [sharing, setSharing] = useState(false);
  return h(
    "article",
    {
      style: {
        ...section,
        borderTop: "1px solid var(--ui-stroke-secondary)",
        paddingTop: "1rem",
        overflowWrap: "anywhere",
      },
    },
    h("h3", null, record.title),
    h(
      "p",
      { style: muted },
      `${plain(record.state)} · ${plain(record.domain)} · ${plain(record.kind)} · ${plain(record.basis)} · revision ${record.revision}`,
    ),
    record.state === "invalidated" &&
      h(
        "p",
        null,
        "Invalidated — its evidence changed. This is not current recall.",
      ),
    record.kind === "procedure" &&
      h("p", null, "Procedure draft only — not an active or executable skill."),
    h("p", { style: { whiteSpace: "pre-wrap" } }, record.text),
    h(
      "details",
      null,
      h("summary", null, "Exact sources and record identity"),
      h("p", null, `Record ${record.id} · Area ${record.scope_id}`),
      (record.sources || []).map((source, index) =>
        h(
          "div",
          { key: index, style: { marginBlock: "0.75rem" } },
          h("code", null, source.ref),
          source.quote &&
            h(
              "blockquote",
              { style: { whiteSpace: "pre-wrap" } },
              source.quote,
            ),
          source.sha256 && h("p", null, `SHA-256: ${source.sha256}`),
          source.revision != null &&
            h("p", null, `Source revision: ${source.revision}`),
        ),
      ),
      h(
        "p",
        null,
        `Dependencies: ${record.dependencies.map((pin) => `${pin.id} (revision ${pin.revision})`).join(", ") || "None"}`,
      ),
    ),
    h(
      "div",
      { style: row },
      button("Correct", () => onEdit(record), pending),
      record.state === "pending" &&
        button(
          "Approve record",
          () =>
            void controller.action(
              `/records/${encodeURIComponent(record.id)}/approve`,
              "POST",
              { expected_revision: record.revision },
            ),
          pending,
        ),
    ),

    h(
      "div",
      { style: row },
      button("Sharing", () => setSharing((v) => !v), pending),
      button(
        "Preview deletion",
        async () => setPreview(await controller.deletionPreview(record)),
        pending,
      ),
    ),
    sharing && h(Sharing, { record, scope, scopes, grants, controller, pending }),
    preview &&
      h(
        "section",
        {
          style: section,
          role: "group",
          "aria-label": "Confirm record deletion",
        },
        h("h4", null, `Delete “${record.title}”?`),
        h(
          "p",
          null,
          `Record revision ${preview.revision}. Dependent records affected: ${preview.dependent_ids.join(", ") || "None"}.`,
        ),
        h(
          "p",
          null,
          "Deletes owned copies and derived content. Host transcripts, unknown exports and backups are outside this operation. This cannot erase earlier model context.",
        ),
        h(
          "div",
          { style: row },
          button(
            "Confirm deletion",
            () =>
              void controller.action(
                `/records/${encodeURIComponent(record.id)}/delete`,
                "POST",
                { preview_token: preview.preview_token },
                "Deleted",
              ),
            pending,
            { variant: "destructive" },
          ),
          button("Keep record", () => setPreview(null), pending),
        ),
      ),
  );
}
function Drafts({ data, scope, controller, pending }) {
  const [ids, setIds] = useState([]);
  const [kind, setKind] = useState("summary");
  const [rebuild, setRebuild] = useState(false);
  const enabled = data.status?.learning_enabled === true;
  const evidence = data.records.filter((r) => r.state === "approved");
  const selectedIds = ids.filter((id) => evidence.some((r) => r.id === id));
  return h(
    "section",
    { style: section, "aria-label": "Drafts and index" },
    h("h2", null, "Drafts and index"),
    h(
      "p",
      null,
      `Draft generation: ${enabled ? "enabled by you" : "off"}. Uses the host model only after opt-in and an explicit request. Results stay pending for review; no diagnoses or automatic skill activation.`,
    ),
    button(
      enabled ? "Disable draft generation" : "Enable draft generation",
      () => void controller.action("/learning", "POST", { enabled: !enabled }),
      pending,
    ),
    enabled &&
      h(
        "div",
        { style: { display: "grid", gap: "0.75rem" } },
        h("p", null, "Choose approved records as evidence for this draft:"),
        evidence.map((r) =>
          h(
            "label",
            { key: r.id, style: row },
            h("input", {
              type: "checkbox",
              disabled: pending,
              checked: ids.includes(r.id),
              "aria-label": `Use ${r.title} as draft evidence`,
              onChange: (e) => {
                const checked = e.target.checked;
                setIds((old) =>
                  checked ? [...old, r.id] : old.filter((id) => id !== r.id),
                );
              },
            }),
            r.title,
          ),
        ),
        !evidence.length &&
          h("p", null, "Approve sourced records before requesting a draft."),
        h(Choice, {
          label: "Draft kind",
          value: kind,
          options: ["summary", "observation", "procedure"],
          onChange: setKind,
          disabled: pending,
        }),
        kind === "observation" && h("p", null,
          "An AI observation is stored as an interpretation (inference), not a directly observed fact. It stays pending until you review it."),
        button(
          "Generate pending draft",
          () => data.model_policy?.mode==="follow_chat"
            ? void requestChatModelDraft(controller,data,scope,selectedIds,kind)
            : void controller.action(
              "/draft",
              "POST",
              { scope_id: scope.id, record_ids: selectedIds, kind, ...(data.context?.policy_revision && data.context.chat_scope_id===scope.id ? {session_id:data.context.session_id} : {}) },
              kind === "observation" ? "Pending AI interpretation requested (observation)" : "Pending draft requested",
            ),
          pending || !selectedIds.length,
        ),
      ),
    h(
      "p",
      { style: muted },
      `Index: ${plain(data.status?.index_state || "unknown")}. Authored records are separate from the replaceable index.`,
    ),
    button("Rebuild index", () => setRebuild(true), pending),
    rebuild &&
      h(
        "section",
        { role: "group", "aria-label": "Confirm index rebuild" },
        h(
          "p",
          null,
          "Build a staged ELM index generation. A failed rebuild must keep the prior valid generation; this UI does not replace indexes itself.",
        ),
        h(
          "div",
          { style: row },
          button(
            "Confirm index rebuild",
            () =>
              void controller.action(
                "/index/rebuild",
                "POST",
                { scope_id: scope.id, confirm: true },
                "Rebuild requested",
              ),
            pending,
          ),
          button("Cancel rebuild", () => setRebuild(false), pending),
        ),
      ),
  );
}
function Privacy({ scope, controller, pending }) {
  const [open, setOpen] = useState(false);
  // The overview cannot prove that a durable chat has never contained messages.
  // Therefore never offer a broadening operation for an existing private chat.
  const cannotBroaden = scope.kind === "chat" && scope.private;
  return h(
    "div",
    null,
    button("Change privacy", () => setOpen((v) => !v), pending),
    open &&
      h(
        "section",
        {
          style: section,
          role: "group",
          "aria-label": "Change memory privacy",
        },
        h(
          "p",
          null,
          "This changes future recall only. It cannot erase earlier messages or model context. Broadening a populated chat is refused; use a fresh chat.",
        ),
        cannotBroaden
          ? h(
              "p",
              null,
              "Start a fresh chat to use a broader boundary. This existing private chat stays private.",
            )
          : button(
              scope.private ? "Allow scoped recall" : "Make area private",
              () =>
                void controller.action("/scopes/privacy", "POST", {
                  scope_id: scope.id,
                  private: !scope.private,
                }),
              pending,
            ),
      ),
  );
}
function Inspector({ data, controller, pending }) {
  const [adding, setAdding] = useState(false);
  // Authored corrections belong to the area, not a revision/topic row that a
  // contradictory readback may replace or remove. Owner/area keys still clear it.
  const [editing, setEditing] = useState(null);
  const scope = data.scopes.find((s) => s.id === data.selected_scope_id);
  const topics = [...new Set(data.records.map((r) => r.topic))];
  return h(
    "div",
    null,
    h(
      "section",
      { style: section, "aria-label": "Memory areas" },
      h("h2", null, "Memory areas"),
      h(
        "p",
        { style: muted },
        "These are your inspector views. Selecting an area does not let the model recall it.",
      ),
      h(
        "div",
        { style: { ...row, alignItems: "start", gap: "1.5rem" } },
        ["personal", "workspace", "chat"].map((kind) =>
          h(
            "section",
            { key: kind, style: { minWidth: 0, flex: "1 1 12rem" } },
            h(
              "h3",
              null,
              kind === "chat"
                ? "Individual chats"
                : kind === "personal"
                  ? "Personal"
                  : "Workspaces",
            ),
            h(
              "ul",
              { style: { listStyle: "none", padding: 0 } },
              data.scopes
                .filter((s) => s.kind === kind)
                .map((s) =>
                  h(
                    "li",
                    { key: s.id, style: { marginBlock: "0.5rem" } },
                    button(
                      `${s.label}${s.private ? " · Private" : " · Scoped"}`,
                      () => void controller.refresh(s.id),
                      pending,
                      {
                        "aria-pressed": s.id === scope.id,
                        style: {
                          maxWidth: "100%",
                          whiteSpace: "normal",
                          textAlign: "left",
                        },
                      },
                    ),
                  ),
                ),
            ),
          ),
        ),
      ),
    ),
    h(
      "section",
      { style: section },
      h("h2", null, scope.label),
      h(
        "p",
        { style: muted },
        `${plain(scope.kind)} memory · ${scope.kind === "personal" ? "Personal facts stay here; only individually approved communication cards may be shared." : scope.private ? "Private container; cannot share its records outward." : "Scoped container; no automatic global sharing."}`,
      ),
      button("Add record", () => setAdding(true), pending),
      h(Privacy, { scope, controller, pending }),
      editing && h(RecordForm, {
        key: editing.id,
        record: editing,
        scope,
        controller,
        pending,
        onClose: () => setEditing(null),
      }),
      adding &&
        h(RecordForm, {
          scope,
          data,
          controller,
          pending,
          onClose: () => setAdding(false),
        }),
      !data.records.length && h("p", null, "No records in this area yet."),
      topics.map((topic) =>
        h(
          "section",
          { key: topic },
          h("h3", null, plain(topic)),
          data.records
            .filter((r) => r.topic === topic)
            .map((record) =>
              h(RecordView, {
                key: `${record.id}:${record.revision}`,
                record,
                scope,
                scopes: data.scopes,
                grants: data.grants,
                controller,
                pending,
                onEdit: setEditing,
              }),
            ),
        ),
      ),
    ),
    h(
      "section",
      { style: section, "aria-label": "Current sharing" },
      h("h2", null, "Current sharing"),
      h("p", { style: muted }, "Human-only active sharing metadata. Inspecting an area or this inventory does not grant model recall."),
      !Array.isArray(data.grants)
        ? h("p", null, "Active sharing inventory unavailable from this API. Requests can be acknowledged, but sharing cannot be independently confirmed.")
        : !data.grants.length
          ? h("p", null, "No active shares in the current inventory.")
          : h("ul", { style: { paddingInlineStart: "1.25rem", overflowWrap: "anywhere" } },
            data.grants.map((g, i) => h("li", { key: i },
              `${data.scopes.find((s) => s.id === g.source_scope)?.label || "Source"} (${g.source_scope}) → ${data.scopes.find((s) => s.id === g.target_scope)?.label || "Target"} (${g.target_scope}) · record ${g.record_id} · granted revision ${g.record_revision}`))),
    ),
    h(Drafts, { data, scope, controller, pending }),
  );
}
function useMemory(controller) {
  const epoch =
    typeof SDK.useGatewayActivationEpoch === "function"
      ? SDK.useGatewayActivationEpoch()
      : null;
  // The public SDK exposes an epoch getter and hook, not an atom. The layout
  // effect clears a same-route activation before stale content can be painted.
  useLayoutEffect(() => controller.reconcile(), [controller, epoch]);
  return useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
}
export function MemoryPage({ controller }) {
  const s = useMemory(controller);
  return h(
    "main",
    {
      style: {
        color: "var(--ui-text-primary)",
        fontSize: "0.875rem",
        lineHeight: 1.55,
        maxWidth: "68rem",
        width: "100%",
        height: "100%",
        overflowY: "auto",
        boxSizing: "border-box",
        marginInline: "auto",
        padding: "1.25rem",
        overflowWrap: "anywhere",
      },
      "aria-label": "Memory",
    },
    h(
      "div",
      { style: row },
      h("h1", { style: { fontSize: "1.4rem", fontWeight: 600 } }, "Memory"),
      button(
        "Refresh",
        () => void controller.refresh(),
        s.pending || ["loading", "refreshing"].includes(s.phase),
      ),
    ),
    h(
      "section",
      { style: section, "aria-label": "Current chat recall boundary" },
      h("h2", null, "Current chat recall"),
      h(
        "p",
        null,
        s.stale
          ? "Boundary not verified — refresh to check current recall."
          : s.data?.context?.boundary ||
              "Boundary unavailable — no memory content is shown.",
      ),
      s.data &&
        h(
          "p",
          { style: muted },
          `${s.data.context.label || "Focused chat"} · ${s.data.context.private ? "Private chat" : "Scoped chat"}`,
        ),
      h(
        "p",
        { style: muted },
        "Private means an isolated memory recall boundary, not encryption or an OS sandbox. Earlier messages and model context are unchanged.",
      ),
    ),
    h(
      "div",
      { role: "status", "aria-live": "polite" },
      s.pending
        ? "Saving…"
        : ["loading", "refreshing"].includes(s.phase)
          ? "Loading memory…"
          : s.notice,
    ),
    s.error && h("p", { role: "alert" }, s.error),
    s.stale &&
      h(
        "p",
        { role: "status" },
        "Previously loaded view — not verified as current. Your draft is retained, but saving is disabled until Refresh succeeds.",
      ),
    s.phase === "unconfigured" &&
      h(
        "section",
        { style: section },
        h("h2", null, "Set up workspace memory"),
        h(
          "p",
          null,
          "Create a fresh profile-owned store. This does not adopt your canonical ELM memory or widen existing permissions.",
        ),
        button(
          "Create fresh memory store",
          () => void controller.action("/setup", "POST", { confirm: true }),
          s.pending || s.unconfirmed,
        ),
      ),
    s.data?.setup &&
      h(Inspector, {
        key: `${s.ownerKey}:${s.data.selected_scope_id}`,
        data: s.data,
        controller,
        pending: s.pending || s.unconfirmed || s.phase !== "ready",
      }),
  );
}
function BoundaryChip({ controller }) {
  const s = useMemory(controller);
  return h(
    "span",
    {
      title:
        s.data?.context?.boundary || s.error || "Memory boundary unavailable",
      style: {
        color: "var(--ui-text-secondary)",
        maxWidth: "20rem",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        display: "inline-block",
      },
    },
    `Memory: ${s.stale ? "boundary not verified" : s.phase === "loading" ? "loading" : s.data?.setup ? s.data.context.boundary : s.phase === "unconfigured" ? "not set up" : "unavailable"}`,
  );
}

// Product-result state deliberately lives outside workspace memory. All REST
// requests remain ambient-only and fail closed for a foreign focused owner.
function productIdentity(host) {
  const s = host?.state || {};
  const session = value(s.focusedStoredSessionId), profile = value(s.focusedSessionProfile);
  const owner = value(s.focusedSessionOwner), connection = value(s.connectionId);
  const ambient = value(s.profile), gateway = value(s.gateway);
  const epoch = typeof SDK.gatewayActivationEpoch === "function" ? SDK.gatewayActivationEpoch() : null;
  const key = JSON.stringify([session, profile, owner, connection, ambient, gateway, epoch]);
  const error = !session ? "Focus a saved chat to view its Important results."
    : !owner?.connectionId || !profile || !connection || !ambient ? "Focused chat ownership is unavailable."
    : owner.profile !== profile || profile !== ambient || owner.connectionId !== connection
      ? "This chat belongs to another profile or gateway. Select its owning gateway first; plugin REST cannot route there."
    : gateway !== "open" ? "The gateway is unavailable. Reconnect, then refresh." : "";
  return {session, profile, key, error};
}
const resultId = (id) => typeof id === "string" && /^[0-9a-f]{32}$/.test(id);
function validResult(r, chat) {
  return r && resultId(r.id) && r.chat_id === chat &&
    ["session_id", "title", "body", "created_at", "updated_at"].every(k => typeof r[k] === "string") &&
    r.title.trim() && [...r.title].length <= 300 && [...r.body].length <= 100000 &&
    ["progress", "partial", "blocked", "final"].includes(r.kind) &&
    ["unread", "viewed", "read"].includes(r.status) && typeof r.dismissed === "boolean" &&
    Number.isSafeInteger(r.revision) && r.revision > 0;
}
const validAttention = p => p && ["quiet", "off"].includes(p.mode) &&
  typeof p.updates_visible === "boolean" && Number.isSafeInteger(p.revision) && p.revision > 0;
function validProductContext(d, session, chat = null) {
  return d?.schema === 1 && d.context?.session_id === session &&
    typeof d.context.chat_id === "string" && d.context.chat_id.length > 0 && (!chat || d.context.chat_id === chat);
}
function validResults(d, session) {
  return validProductContext(d, session) && Array.isArray(d.results) &&
    d.results.every(r => validResult(r, d.context.chat_id)) &&
    new Set(d.results.map(r => r.id)).size === d.results.length && validAttention(d.attention) &&
    ["unread", "viewed", "read", "dismissed"].every(k => Number.isSafeInteger(d.counts?.[k]) && d.counts[k] >= 0) &&
    (d.next_cursor === null || typeof d.next_cursor === "string" && /^[1-9][0-9]{0,17}$/.test(d.next_cursor));
}
export function createImportantController(ctx, host = SDK.host) {
  let disposed = false, generation = 0, ownerKey = "", showDismissed = false;
  let snapshot = {data:null, phase:"idle", pending:false, unconfirmed:false, error:"", notice:"", ownerKey:"", detail:null};
  const listeners = new Set();
  const publish = change => {snapshot = {...snapshot, ...change}; for (const fn of listeners) fn();};
  function sync() {
    const identity = productIdentity(host);
    if (identity.key !== ownerKey) {
      ownerKey = identity.key; generation++; showDismissed = false;
      publish({data:null, detail:null, phase:identity.error ? "unavailable" : "idle", error:identity.error,
        pending:false, unconfirmed:false, notice:"", ownerKey});
    }
    return identity;
  }
  const live = (token,key) => !disposed && token === generation && productIdentity(host).key === key;
  const query = (session, extra={}) => new URLSearchParams({session_id:session, ...extra});
  async function list(current, cursor = null) {
    const d = await ctx.rest(`/ui/results?${query(current.session, {limit:"100", include_dismissed:String(showDismissed), ...(cursor ? {cursor} : {})})}`, {timeoutMs:20000});
    if (!validResults(d,current.session)) throw Error("Important results returned an incompatible chat, result or schema. Nothing was loaded.");
    return d;
  }
  async function refresh(options = {}) {
    const current = sync();
    if (disposed || current.error || snapshot.pending) return false;
    const before = snapshot.data, detail = snapshot.detail;
    const filterChanged = typeof options.showDismissed === "boolean" && options.showDismissed !== showDismissed;
    if (typeof options.showDismissed === "boolean") showDismissed = options.showDismissed;
    const token = ++generation, key = current.key;
    // Same-owner refresh is non-destructive: keyed cards, disclosures and
    // optional update review stay mounted until the new read is verified.
    publish({phase:before ? "refreshing" : "loading", pending:true, error:"", notice:""});
    try {
      let d = await list(current);
      if (!live(token,key)) return false;
      if (before && d.context.chat_id !== before.context.chat_id) throw Error("The chat lineage changed. Refresh first.");
      const boundary = !filterChanged && before?.results.at(-1)?.id;
      const cursors = new Set();
      while (boundary && !d.results.some(r=>r.id===boundary) && d.next_cursor) {
        if (cursors.has(d.next_cursor) || d.results.length >= 1000) throw Error("The result pages changed. Refresh before continuing.");
        cursors.add(d.next_cursor);
        const page = await list(current,d.next_cursor);
        if (!live(token,key)) return false;
        if (page.context.chat_id !== d.context.chat_id) throw Error("The chat lineage changed. Refresh first.");
        const results = [...d.results,...page.results];
        if (new Set(results.map(r=>r.id)).size !== results.length) throw Error("The result pages changed. Refresh before continuing.");
        d = {...page,results};
      }
      const observed = detail ? await exact(current,detail.id,d.context.chat_id) : null;
      if (!live(token,key)) return false;
      publish({data:d, detail:observed?.exists ? observed.result : null, phase:"ready", pending:false, unconfirmed:false, notice:"", showDismissed});
      return true;
    } catch (e) {
      if (live(token,key)) publish({phase:"error", pending:false, error:e.message || "Results could not be loaded."});
      return false;
    }
  }
  async function more() {
    const current = sync(), before = snapshot.data;
    if (disposed || current.error || snapshot.pending || !before?.next_cursor || snapshot.unconfirmed) return false;
    const token = ++generation, key = current.key;
    publish({pending:true, error:""});
    try {
      const d = await list(current,before.next_cursor);
      if (!live(token,key)) return false;
      if (d.context.chat_id !== before.context.chat_id) throw Error("The chat lineage changed. Refresh first.");
      const merged = [...before.results, ...d.results];
      if (new Set(merged.map(r=>r.id)).size !== merged.length) throw Error("The result pages changed. Refresh before continuing.");
      publish({data:{...d, results:merged}, pending:false}); return true;
    } catch(e) {if (live(token,key)) publish({pending:false,error:e.message}); return false;}
  }
  async function exact(current,id,chat) {
    const d = await ctx.rest(`/ui/results/${id}?${query(current.session)}`, {timeoutMs:20000});
    if (!validProductContext(d,current.session,chat) || d.id !== id || typeof d.exists !== "boolean" ||
        (d.exists ? !validResult(d.result,d.context.chat_id) || d.result.id !== id : d.result !== null))
      throw Error("The exact result readback could not be verified.");
    return d;
  }
  async function openResult(id, pin) {
    const current=sync();
    if (disposed || current.error || pin !== ownerKey || !resultId(id) || snapshot.pending) return false;
    const token=++generation,key=current.key;
    publish({detail:null,error:""});
    try {
      const d=await exact(current,id,snapshot.data?.context.chat_id);
      if (!live(token,key)) return false;
      publish({detail:d.exists ? d.result : null,notice:d.exists ? "" : "This saved result is unavailable in the focused chat (deleted, compacted away, or owned elsewhere)."});return d.exists;
    } catch(e){if(live(token,key))publish({error:e.message});return false;}
  }
  function writable(pin) {
    const current = sync();
    return !disposed && !current.error && pin === ownerKey && snapshot.data &&
      snapshot.phase === "ready" && !snapshot.pending && !snapshot.unconfirmed ? current : null;
  }
  async function write(pin, operation) {
    const current = writable(pin);
    if (!current) return false;
    const token = ++generation, key = current.key;
    publish({pending:true, error:"", notice:"Saving…"});
    try {
      const change = await operation(current, () => live(token,key));
      if (!live(token,key)) return false;
      publish({...change, pending:false, unconfirmed:false, notice:"Saved and verified by exact readback."});return true;
    } catch(e) {
      if (live(token,key)) publish({pending:false, unconfirmed:true, error:e.message || "The write failed.",
        notice:"Outcome unconfirmed. Refresh to reconcile before another action; nothing is retried automatically."});
      return false;
    }
  }
  async function mutate(r, action, pin) {
    if (!["view","read","dismiss","restore","delete"].includes(action)) return false;
    return write(pin, async (current, stillLive) => {
      const before = snapshot.data;
      const known = before.results.find(x=>x.id===r.id) || (snapshot.detail?.id === r.id ? snapshot.detail : null);
      if (!known || !same(known,r)) throw Error("This result is stale. Refresh and review first.");
      const path = `/ui/results/${r.id}${action === "delete" ? "" : `/${action}`}`;
      const receipt = await ctx.rest(path, {method:action === "delete" ? "DELETE" : "POST",
        body:{session_id:current.session, expected_revision:r.revision},timeoutMs:20000});
      if (!stillLive()) throw Error("Chat changed during the write.");
      const observed = await exact(current,r.id,before.context.chat_id);
      if (!stillLive()) throw Error("Chat changed during readback.");
      const result=receipt?.result;
      if (receipt?.ok !== true) throw Error(receipt?.message || "The write was not acknowledged.");
      if (action === "delete") {
        if (result?.deleted_id !== r.id || result.deleted_revision !== r.revision || observed.exists)
          throw Error("Deletion was not confirmed for the exact result revision.");
      } else {
        const intendedStatus = action === "read" ? "read" : action === "view" && r.status === "unread" ? "viewed" : r.status;
        const intendedDismissed = action === "dismiss" ? true : action === "restore" ? false : r.dismissed;
        const changed = intendedStatus !== r.status || intendedDismissed !== r.dismissed;
        if (!observed.exists || !same(observed.result,result) || !validResult(result,before.context.chat_id) ||
            result.id !== r.id || result.status !== intendedStatus || result.dismissed !== intendedDismissed ||
            result.revision !== r.revision + Number(changed) ||
            ["title","body","kind","session_id","created_at"].some(k=>result[k] !== r[k]))
          throw Error("The exact result does not match the requested change.");
      }
      const d=await list(current);
      if (d.context.chat_id !== before.context.chat_id) throw Error("Chat changed during refresh.");
      // The exact readback certifies this target, not a replacement first page.
      // Keep the loaded keyset/cursor so opening older output cannot evict it.
      const results=before.results.flatMap(row=>row.id !== r.id ? [row]
        : observed.exists && (showDismissed || !observed.result.dismissed) ? [observed.result] : []);
      return {data:{...d,results,next_cursor:before.next_cursor},
        detail:snapshot.detail?.id === r.id ? observed.result : snapshot.detail};
    });
  }
  async function setAttention(changes,pin) {
    return write(pin, async (current,stillLive) => {
      if (!changes || Object.keys(changes).sort().join(',') !== 'mode,updates_visible' || !["quiet","off"].includes(changes.mode) || typeof changes.updates_visible !== "boolean")
        throw Error("Unsupported attention preferences.");
      const old=snapshot.data.attention, chat=snapshot.data.context.chat_id;
      const receipt=await ctx.rest('/ui/attention',{method:"POST",body:{session_id:current.session,expected_revision:old.revision,...changes},timeoutMs:20000});
      if(!stillLive())throw Error("Chat changed during preference save.");
      const d=await ctx.rest(`/ui/attention?${query(current.session)}`,{timeoutMs:20000});
      if(!validProductContext(d,current.session,chat) || receipt?.ok !== true || !validAttention(receipt.result) ||
          !same(receipt.result,d.attention) || !contains(receipt.result,changes) || receipt.result.revision !== old.revision+1)
        throw Error("The preference receipt and independent readback do not match the requested value.");
      return {data:{...snapshot.data,attention:d.attention}};
    });
  }
  function reconcile(){sync();}
  const unlisten=["focusedStoredSessionId","focusedSessionProfile","focusedSessionOwner","profile","connectionId","gateway"]
    .map(k=>host?.state?.[k]).filter(a=>typeof a?.listen === "function").map(a=>a.listen(reconcile));
  sync();
  return {getSnapshot:()=>snapshot, subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},
    refresh,more,mutate,setAttention,openResult,reconcile,
    dispose(){disposed=true;generation++;for(const fn of unlisten)fn();listeners.clear();}};
}

// Native updater state is independent of memory and invalidates with the same
// public host ownership/lifetime tuple as the result inbox.
const updateKey = r => `${r.type}:${r.name}`;
const validUpdate = r => r && ["skill","plugin"].includes(r.type) &&
  ["name","source","identifier","current","target","status","detail"].every(k=>typeof r[k] === "string") &&
  typeof r.selectable === "boolean" && (!r.selectable || r.status === "update_available" &&
    (r.type === "skill" ? /^sha256:[0-9a-f]{16}$/.test(r.target) : /^[0-9a-fA-F]{40}$/.test(r.target)));
export function createUpdatesController(ctx, host = SDK.host) {
  let disposed=false,generation=0,key="";
  let snapshot={rows:[],errors:[],outcomes:[],phase:"idle",pending:false,unconfirmed:false,error:"",ownerKey:"",policy:""};
  const listeners=new Set(),publish=change=>{snapshot={...snapshot,...change};for(const fn of listeners)fn();};
  function sync(){const i=productIdentity(host);if(i.key!==key){key=i.key;generation++;publish({rows:[],errors:[],outcomes:[],phase:i.error?"unavailable":"idle",pending:false,unconfirmed:false,error:i.error,ownerKey:key,policy:""});}return i;}
  const live=(t,k)=>!disposed && t===generation && productIdentity(host).key===k;
  async function check(){
    const i=sync();if(disposed || i.error || snapshot.pending)return false;
    const token=++generation,k=i.key;
    publish({phase:"checking",pending:true,rows:[],errors:[],error:""});
    try{
      const d=await ctx.rest('/ui/updates/check',{method:"POST",body:{session_id:i.session},timeoutMs:120000});
      if(!live(token,k))return false;
      if(!validProductContext(d,i.session) || !Array.isArray(d.rows) || !d.rows.every(validUpdate) || new Set(d.rows.map(updateKey)).size!==d.rows.length ||
        !Array.isArray(d.errors) || !d.errors.every(e=>["skill","plugin"].includes(e?.type) && typeof e.message==="string") || typeof d.policy!=="string")
        throw Error("Native update inventory is incompatible or incomplete; no updates can be selected.");
      publish({rows:d.rows,errors:d.errors,policy:d.policy,phase:"ready",pending:false,unconfirmed:false,chat:d.context.chat_id});return true;
    }catch(e){if(live(token,k))publish({phase:"error",pending:false,error:e.message});return false;}
  }
  async function apply(selected,pin){
    const i=sync();
    if(disposed || i.error || pin!==key || snapshot.pending || snapshot.unconfirmed || snapshot.phase!=="ready" ||
      !Array.isArray(selected) || !selected.length || new Set(selected.map(updateKey)).size!==selected.length ||
      !selected.every(r=>r.selectable && snapshot.rows.some(x=>same(x,r))))return false;
    const token=++generation,k=i.key,outcomes=[];
    publish({pending:true,error:"",outcomes:[],phase:"applying"});
    for(const r of selected){
      try{
        // Never re-check/replace a user's selection with a newer inferred target.
        const receipt=await ctx.rest('/ui/updates/apply',{method:"POST",body:{session_id:i.session,selection:r},timeoutMs:180000});
        if(!live(token,k))return false;
        const d=await ctx.rest(`/ui/updates/installed?${new URLSearchParams({session_id:i.session,type:r.type,name:r.name})}`,{timeoutMs:20000});
        if(!live(token,k))return false;
        const result=receipt?.result;
        if(receipt?.ok!==true || !contains(result,{type:r.type,name:r.name,current:r.current,target:r.target,observed:r.target,status:"updated"}) ||
            !validProductContext(d,i.session,snapshot.chat) || d.type!==r.type || d.name!==r.name || d.observed!==r.target)
          throw Error("The selected native update's exact installed target is unconfirmed.");
        outcomes.push({key:updateKey(r),status:"updated",detail:result.detail || "Exact installed target verified."});
        publish({outcomes:[...outcomes],rows:snapshot.rows.map(x=>updateKey(x)===updateKey(r)?{...x,selectable:false,status:"updated"}:x)});
      }catch(e){
        if(live(token,k)){
          outcomes.push({key:updateKey(r),status:"failed or unknown",detail:e.message});
          publish({outcomes,pending:false,phase:"error",unconfirmed:true,error:"Update stopped. Check installed state before another selection; no failed or remaining item is retried automatically."});
        }
        return false;
      }
    }
    publish({outcomes,pending:false,phase:"ready"});return true;
  }
  const unlisten=["focusedStoredSessionId","focusedSessionProfile","focusedSessionOwner","profile","connectionId","gateway"].map(k=>host?.state?.[k]).filter(a=>typeof a?.listen==="function").map(a=>a.listen(sync));
  sync();return {getSnapshot:()=>snapshot,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},check,apply,reconcile:()=>{sync();},dispose(){disposed=true;generation++;unlisten.forEach(f=>f());listeners.clear();}};
}

function useImportant(controller) {
  const s=useMemory(controller);
  useLayoutEffect(()=>{if(s.phase === "idle")void controller.refresh();},[controller,s.ownerKey,s.phase]);
  return s;
}
function ResultCard({result:r,controller,ownerKey,disabled,ctx,initialExpanded=false}) {
  const [expanded,setExpanded]=useState(initialExpanded),[confirm,setConfirm]=useState(false),[copy,setCopy]=useState("");
  useLayoutEffect(()=>{if(initialExpanded && r.status==="unread")void controller.mutate(r,"view",ownerKey);},[controller,ownerKey,r.id,initialExpanded]);
  async function open(){setExpanded(v=>!v);if(!expanded && r.status==="unread")await controller.mutate(r,"view",ownerKey);}
  return h("article",{style:{...section,borderTop:"1px solid var(--ui-stroke-secondary)",paddingTop:"1rem",minWidth:0}},
    h("h2",{style:{fontSize:"1.1rem",fontWeight:600,margin:0}},r.title),
    h("p",{style:{...muted,margin:0}},`${r.status === "unread" ? "Unread" : r.status === "viewed" ? "Viewed" : "Read · acknowledged by you"} · ${plain(r.kind)}${r.dismissed ? " · Dismissed" : ""}`),
    h("div",{style:row},button(expanded?"Hide result":"View result",()=>void open(),disabled,{"aria-expanded":expanded}),
      r.status!=="read" && button("Mark read",()=>void controller.mutate(r,"read",ownerKey),disabled),
      button(r.dismissed?"Restore":"Dismiss",()=>void controller.mutate(r,r.dismissed?"restore":"dismiss",ownerKey),disabled),
      button("Delete",()=>setConfirm(true),disabled)),
    expanded && h("div",{style:{display:"grid",gap:"0.75rem",minWidth:0}},
      h("div",{style:{whiteSpace:"pre-wrap",overflowWrap:"anywhere",lineHeight:1.65}},r.body),
      button("Copy full result",async()=>{let ok=false;try{ok=await ctx?.os?.writeClipboard?.(r.body);}catch{}setCopy(ok?"Copied full result.":"Clipboard unavailable. Select the result text to copy it.");},disabled),
      copy && h("p",{role:"status"},copy),
      h("details",null,h("summary",null,"Saved result identity"),h("p",{style:muted},`Result ${r.id} · revision ${r.revision} · saved ${r.created_at}. Saved output is separate from the host transcript; deleting it does not erase chat history or earlier model context.`))),
    confirm && h("section",{role:"group","aria-label":"Confirm result deletion",style:{display:"grid",gap:"0.75rem"}},
      h("p",null,`Delete “${r.title}” from this chat’s saved results? This cannot be undone. The host transcript is unchanged.`),
      h("div",{style:row},button("Confirm delete result",()=>void controller.mutate(r,"delete",ownerKey),disabled,{variant:"destructive"}),button("Keep result",()=>setConfirm(false),disabled))));
}
function UpdatesSection({controller}) {
  const s=useMemory(controller),[selected,setSelected]=useState([]),[review,setReview]=useState(false);
  const chosen=s.rows.filter(r=>r.selectable && selected.includes(updateKey(r)));
  return h("section",{style:section,"aria-label":"Optional updates"},
    h("h2",null,"Updates"),
    h("p",{style:muted},"Check hub-installed skills only when you ask. Plugin updates are disabled in this catalog build; use Hermes native plugin controls. Select exact skill targets below. Native-detected local edits are kept; scan cautions require native review. No new skill packs, forced updates, auto-update changes or plugin activation here."),
    button("Check native updates",()=>{setSelected([]);setReview(false);void controller.check();},s.pending || s.phase==="unavailable"),
    s.pending && h("p",{role:"status"},s.phase==="checking"?"Checking native update APIs…":"Applying only the confirmed selections…"),
    s.error && h("p",{role:"alert"},s.error),
    s.errors.map((e,i)=>h("p",{key:i,role:"alert"},`${e.type} check unavailable: ${e.message}. Unknown is not up to date.`)),
    s.phase==="ready" && !s.rows.length && h("p",null,"No installed items returned by the available native checkers."),
    s.rows.map(r=>h("div",{key:updateKey(r),style:{display:"grid",gap:"0.35rem",borderTop:"1px solid var(--ui-stroke-secondary)",paddingBlock:"0.75rem",minWidth:0}},
      h("label",{style:row},h("input",{type:"checkbox",checked:chosen.some(x=>updateKey(x)===updateKey(r)),disabled:s.pending||s.unconfirmed||!r.selectable,
        "aria-label":`Select ${r.type} ${r.name}`,onChange:e=>{const checked=e.target.checked;setReview(false);setSelected(old=>checked?[...old,updateKey(r)]:old.filter(k=>k!==updateKey(r)));}}),`${r.name} · ${r.type} · ${plain(r.status)}`),
      h("p",{style:{...muted,margin:0}},`${r.source} · installed: ${r.current || "unknown"} → target: ${r.target || "unknown"}`),r.detail && h("p",{style:{margin:0}},r.detail))),
    chosen.length>0 && button(`Review ${chosen.length} selected update${chosen.length===1?"":"s"}`,()=>setReview(true),s.pending||s.unconfirmed),
    review && chosen.length>0 && h("section",{role:"group","aria-label":"Confirm selected native updates",style:section},
      h("h3",null,"Apply these exact selections?"),h("ul",null,chosen.map(r=>h("li",{key:updateKey(r)},`${r.type} ${r.name}: ${r.current} → ${r.target}`))),
      h("p",null,"Each installed skill target is independently read back. The batch stops on failure or an unknown outcome; remaining items are not retried."),
      h("div",{style:row},button("Confirm selected updates",()=>{setReview(false);void controller.apply(chosen,s.ownerKey);},s.pending||s.unconfirmed),button("Cancel updates",()=>setReview(false),s.pending))),
    s.outcomes.length>0 && h("ul",{"aria-label":"Update outcomes"},s.outcomes.map(o=>h("li",{key:o.key},`${o.key} · ${o.status}: ${o.detail}`))));
}
export function ImportantPage({controller,updates,ctx}) {
  const s=useImportant(controller),d=s.data;
  const disabled=s.pending||s.unconfirmed||s.phase!=="ready";
  const detail=s.detail;
  return h("main",{"aria-label":"Important results",style:{color:"var(--ui-text-primary)",fontSize:"0.9375rem",lineHeight:1.55,maxWidth:"62rem",width:"100%",height:"100%",overflowY:"auto",boxSizing:"border-box",marginInline:"auto",padding:"1.25rem",overflowWrap:"anywhere"}},
    h("div",{style:row},h("h1",{style:{fontSize:"1.5rem",fontWeight:600}},"Important results"),button("Refresh results",()=>void controller.refresh(),s.pending||s.phase==="loading")),
    h("p",{style:muted},"Saved assistant output for the focused chat. Important is not a user memory fact or proof the whole request is complete. Opening says Viewed; only Mark read records your acknowledgment. No forced scrolling or notifications."),
    h("div",{role:"status","aria-live":"polite"},s.phase==="loading"?"Loading this chat’s results…":s.phase==="refreshing"?"Refreshing this chat’s results; the previous view remains visible…":s.notice),
    s.error && h("p",{role:"alert"},s.error),
    d && h("div",{key:s.ownerKey},
      h("p",{style:muted},`${d.counts.unread} unread · ${d.counts.viewed} viewed · ${d.counts.read} read · ${d.counts.dismissed} dismissed. Chat ${d.context.session_id}.`),
      h("section",{style:section,"aria-label":"Attention preferences"},
        h("h2",null,"Attention"),
        h(Choice,{label:"Important result attention",value:d.attention.mode,disabled,options:[{value:"quiet",label:"Quiet count only"},{value:"off",label:"Off · no unread count in status bar"}],onChange:mode=>void controller.setAttention({mode,updates_visible:d.attention.updates_visible},s.ownerKey)}),
        h("label",{style:row},h("input",{type:"checkbox","aria-label":"Show dismissed results",checked:Boolean(s.showDismissed),disabled:s.pending,onChange:e=>void controller.refresh({showDismissed:e.target.checked})}),"Show dismissed results"),
        h("label",{style:row},h("input",{type:"checkbox","aria-label":"Show update controls",checked:d.attention.updates_visible,disabled,onChange:e=>void controller.setAttention({mode:d.attention.mode,updates_visible:e.target.checked},s.ownerKey)}),"Show update controls")),
      detail && h(ResultCard,{key:`detail:${detail.id}`,result:detail,controller,ownerKey:s.ownerKey,disabled,ctx,initialExpanded:true}),
      !d.results.length && !detail && h("p",null,"No saved results in this view."),
      d.results.filter(r=>r.id!==detail?.id).map(r=>h(ResultCard,{key:r.id,result:r,controller,ownerKey:s.ownerKey,disabled,ctx})),
      d.next_cursor && button("Load older results",()=>void controller.more(),disabled),
      d.attention.updates_visible && updates && h(UpdatesSection,{key:s.ownerKey,controller:updates})));
}
function ImportantChip({controller}) {
  const s=useImportant(controller),d=s.data;
  return button(`Important${d?.attention.mode==="quiet"?` · ${d.counts.unread} unread`:""}`,()=>SDK.host.navigate('/elm-important'),false,{title:s.error||"Open saved results for the focused chat",variant:"ghost"});
}
function ImportantDirective({attrs,controller,ctx}) {
  const s=useImportant(controller),id=attrs?.id;
  if(!resultId(id))return h("span",null,"Saved result reference is invalid.");
  return h("aside",{style:{borderInlineStart:"2px solid var(--ui-stroke-secondary)",paddingInlineStart:"0.75rem",marginBlock:"0.75rem"}},
    h("p",{style:muted},"Important · saved output, not a whole-task completion receipt"),
    button("Open saved result in Important results",async()=>{if(await controller.openResult(id,s.ownerKey))SDK.host.navigate('/elm-important');},s.pending||!s.data),
    s.notice && h("p",{role:"status"},s.notice),s.error && h("p",{role:"alert"},s.error));
}

// Private creation/defaults: separate from normal host creation and memory facts.
// Human-only processing: snapshot the native live chat route, never the global
// auxiliary default. The backend rechecks source, identity and host trust gates.
export async function requestChatModelDraft(controller,data,scope,recordIds,kind,host=SDK.host){
  const before=controller.getSnapshot(),owner=productIdentity(host),runtime=value(host?.state?.focusedSessionId);
  const ids=[...recordIds];
  if(before.data!==data||owner.error||owner.session!==data.context?.session_id||scope.id!==data.selected_scope_id||typeof runtime!=="string"||!runtime)return false;
  let options;
  try{options=await host.request("model.options",{session_id:runtime,explicit_only:true,include_unconfigured:false,refresh:false});}
  catch{host.notify?.({kind:"error",message:"Current chat model could not be verified; no draft was requested."});return false;}
  const now=controller.getSnapshot();
  if(now.ownerKey!==before.ownerKey||now.data!==data||productIdentity(host).key!==owner.key||value(host?.state?.focusedSessionId)!==runtime)return false;
  const provider=options?.provider,model=options?.model;
  if(typeof provider!=="string"||!provider||typeof model!=="string"||!model||!options.providers?.some(p=>p.slug===provider&&p.authenticated===true&&p.models?.includes(model)&&!p.unavailable_models?.includes(model))){
    host.notify?.({kind:"error",message:"The current model is not in the verified native inventory; no draft was requested."});return false;
  }
  return controller.action("/draft","POST",{scope_id:scope.id,record_ids:ids,kind,session_id:owner.session,model_route:{provider,model}},"Generate pending draft");
}

const privateClone = x => JSON.parse(JSON.stringify(x));
const privateStable = x => JSON.stringify(x && typeof x === "object" ? Array.isArray(x) ? x.map(v=>JSON.parse(privateStable(v))) : Object.fromEntries(Object.keys(x).sort().map(k=>[k,JSON.parse(privateStable(x[k]))])) : x);
function validPrivateSettings(s) {
  if(!s || Object.keys(s).sort().join()!=="cap_enabled,private_chat,private_workspace" || s.cap_enabled!==false)return false;
  const literal=v=>typeof v==="string"&&v.length<=256&&v===v.trim()&&!/[\x00-\x1f\x7f]/.test(v);
  return ["private_chat","private_workspace"].every(k=>{const e=s[k],c=e?.conversation,m=e?.memory;
    return e&&Object.keys(e).sort().join()==="conversation,memory,workspace_reads"&&typeof e.workspace_reads==="boolean"&&c&&Object.keys(c).sort().join()==="model,provider"&&m&&Object.keys(m).sort().join()==="allow_host_fallback,mode,model,provider"&&
      [c,m].every(r=>literal(r.provider)&&literal(r.model)&&!!r.provider===!!r.model)&&["host","follow_chat","separate"].includes(m.mode)&&typeof m.allow_host_fallback==="boolean"&&(m.mode==="separate")===!!m.provider;});
}
export function createPrivateController(ctx,host=SDK.host) {
  let disposed=false,generation=0,key="",listeners=new Set();
  let state={ownerKey:"",data:null,choices:[],pending:false,unconfirmed:false,saveUnknown:false,error:"",notice:"",intent:null,created:null,ready:false};
  const publish=p=>{state={...state,...p};for(const f of listeners)f();};
  function sync(){if(disposed)return {session:"",key:"",error:"Private controls disposed"};const c=productIdentity(host);c.key=JSON.stringify([c.key,value(host?.state?.focusedSessionId)]);
    if(c.key!==key){key=c.key;generation++;publish({ownerKey:key,data:null,choices:[],pending:false,unconfirmed:false,saveUnknown:false,error:c.error,notice:"",intent:null,created:null,ready:false});}return c;}
  const live=(t,k)=>!disposed&&t===generation&&sync().key===k;
  const canWrite=c=>!disposed&&!c.error&&!state.pending&&!state.unconfirmed&&!state.saveUnknown&&state.ready;
  const get=(path,c,extra={})=>ctx.rest(path+"?"+new URLSearchParams({session_id:c.session,...extra}),{timeoutMs:20000});
  const post=async(path,c,body)=>{const d=await ctx.rest(path,{method:"POST",body:{session_id:c.session,...body},timeoutMs:20000});if(d?.ok!==true||!d.result)throw Error("Unconfirmed private-control write");return d.result;};
  const valid=(d,c)=>validProductContext(d,c.session)&&Number.isSafeInteger(d.revision)&&d.revision>0&&validPrivateSettings(d.settings)&&typeof d.memory_setup==="boolean"&&Array.isArray(d.projects)&&d.projects.every(p=>typeof p.id==="string"&&typeof p.name==="string"&&typeof p.private_workspace==="boolean");
  async function inventory(){try{const d=await host.request("model.options",{session_id:value(host.state?.focusedSessionId),explicit_only:true,include_unconfigured:false,refresh:false});
    if(!Array.isArray(d?.providers))return[];return d.providers.flatMap(p=>p.authenticated===true&&typeof p.slug==="string"&&Array.isArray(p.models)?p.models.filter(m=>typeof m==="string"&&!p.unavailable_models?.includes(m)).map(model=>({provider:p.slug,model})):[]);}catch{return[];}}
  const admitted=(settings,choices)=>validPrivateSettings(settings)&&["private_chat","private_workspace"].every(k=>[settings[k].conversation,settings[k].memory].every(r=>!r.provider||choices.some(v=>v.provider===r.provider&&v.model===r.model)));
  async function refresh(){const c=sync();if(disposed||c.error||state.pending)return false;const t=++generation;publish({pending:true,error:""});
    try{const [d,choices]=await Promise.all([get('/ui/private',c),inventory()]);if(!live(t,c.key))return false;if(!valid(d,c))throw Error('Private controls schema/owner mismatch');
      const pending=Array.isArray(d.pending)?d.pending:[];publish({data:privateClone(d),choices,pending:false,ready:true,saveUnknown:false,unconfirmed:state.unconfirmed||pending.length>0,intent:state.intent||(pending[0]?{id:pending[0].id}:null)});return true;
    }catch{if(live(t,c.key))publish({pending:false,ready:false,error:'Private controls could not be verified. Refresh before writing.'});return false;}}
  async function save(settings){const c=sync();if(!canWrite(c))return false;const t=++generation,revision=state.data.revision;publish({pending:true,error:""});let wrote=false;
    try{settings=privateClone(settings);const choices=await inventory();if(!live(t,c.key))return false;if(!admitted(settings,choices))throw Error('Choose currently authenticated/available exact model IDs, or native inheritance');
      wrote=true;const saved=await post('/ui/private/defaults',c,{expected_revision:revision,settings});if(!live(t,c.key))return false;const d=await get('/ui/private',c);if(!live(t,c.key))return false;
      if(!valid(d,c)||saved.revision!==revision+1||d.revision!==saved.revision||privateStable(d.settings)!==privateStable(settings)||privateStable(saved.settings)!==privateStable(settings))throw Error('Exact defaults readback differs');
      publish({data:privateClone(d),choices,pending:false,saveUnknown:false,notice:'Defaults saved and independently read back. Existing containers are unchanged.'});return true;
    }catch(e){if(live(t,c.key))publish({pending:false,saveUnknown:wrote,error:wrote?'Defaults may have committed. Refresh; never retry automatically.':e.message});return false;}}
  async function create(kind,projectId="",name=""){const c=sync();if(!canWrite(c)||!state.data.memory_setup)return false;
    if(!["private_chat","workspace_member","private_workspace"].includes(kind))return false;
    const t=++generation,revision=state.data.revision;publish({pending:true,error:"",notice:"",created:null});let nativeAttempted=false;
    try{const choices=await inventory();if(!live(t,c.key))return false;
      if(kind!=="workspace_member"&&!admitted(state.data.settings,choices))throw Error('A selected route is not available. Choose another before creating.');
      const intent=await post('/ui/private/create',c,{kind,project_id:projectId,name,expected_revision:revision});if(!live(t,c.key))return false;
      const p=intent.params,wsp=kind==="private_workspace";
      if(!validProductContext(intent,c.session)||!resultId(intent.id)||intent.method!==(wsp?'projects.create':'session.create')||!p||Object.keys(p).some(k=>!(wsp?["name","use","create_directory"]:["request_id","source","project_id","provider","model","follow_profile_config"]).includes(k)))throw Error('Unexpected native creation contract');
      if(wsp?(p.name!==name||p.use!==false||p.create_directory!==false):(p.request_id!==intent.id||p.source!=="gui"||(p.project_id||"")!==projectId||!!p.provider!==!!p.model||p.provider&&(!choices.some(v=>v.provider===p.provider&&v.model===p.model)||p.follow_profile_config!==false)))throw Error('Native target or route differs');
      publish({intent});const before=await get('/ui/private/status',c,{intent_id:intent.id});if(!live(t,c.key))return false;if(before.id!==intent.id||before.state!=="ready")throw Error('Intent not ready');
      nativeAttempted=true;const native=await host.request(intent.method,privateClone(p));if(!live(t,c.key))return false;
      const id=wsp?native?.project?.id:native?.stored_session_id;
      if(typeof id!=="string"||!id||id.length>256||!wsp&&native.message_count!==0)throw Error('Native outcome unknown');
      const done=await post('/ui/private/finish',c,{intent_id:intent.id,created_id:id});if(!live(t,c.key))return false;
      const observed=await get('/ui/private/status',c,{intent_id:intent.id});if(!live(t,c.key))return false;
      if(done.id!==intent.id||done.created_id!==id||done.kind!==kind||done.status!=="configured"||observed.id!==intent.id||observed.state!=="applied"||observed.target!==id||privateStable(observed.outcome)!==privateStable(done))throw Error('Creation not confirmed');
      publish({pending:false,intent:null,created:privateClone(done),notice:'Native container created and privacy configuration read back. Nothing was installed or globally changed.'});await refresh();return true;
    }catch(e){if(live(t,c.key))publish({pending:false,unconfirmed:nativeAttempted,error:nativeAttempted?'Native creation may have happened. Inspect the native list; do not repeat.':e.message});return false;}}
  async function reconcile(){const c=sync();if(c.error||state.pending||!state.intent)return false;const t=++generation;publish({pending:true,error:""});
    try{const d=await get('/ui/private/status',c,{intent_id:state.intent.id});if(!live(t,c.key))return false;if(d.state!=="applied"||d.outcome?.status!=="configured")throw Error();
      publish({pending:false,unconfirmed:false,intent:null,created:d.outcome,notice:'Prior creation confirmed by status; nothing was repeated.'});await refresh();return true;
    }catch{if(live(t,c.key))publish({pending:false,error:'Outcome remains unconfirmed; inspect the native list.'});return false;}}
  async function abandon(){const c=sync();if(c.error||state.pending||!state.intent)return false;const id=state.intent.id,t=++generation;publish({pending:true});
    try{await post('/ui/private/abandon',c,{intent_id:id,confirm:true});if(!live(t,c.key))return false;const d=await get('/ui/private/status',c,{intent_id:id});if(!live(t,c.key))return false;if(d.id!==id||!["closed","applied"].includes(d.state))throw Error();
      publish({pending:false,unconfirmed:false,intent:null,notice:'Attempt closed after your inspection. No container was deleted or creation retried.'});await refresh();return true;
    }catch{if(live(t,c.key))publish({pending:false,error:'Attempt close is unconfirmed.'});return false;}}
  async function currentReads(enabled){const c=sync(),v=state.data?.current_policy;if(!canWrite(c)||!v)return false;const t=++generation;publish({pending:true,error:""});
    try{await post('/read-policy',c,{workspace_enabled:enabled,expected_identity:v.identity,expected_policy_revision:v.policy_revision});if(!live(t,c.key))return false;const d=await get('/read-policy',c);if(!live(t,c.key))return false;if(d.workspace_enabled!==enabled||d.authored_scope_id!==v.authored_scope_id||!d.private)throw Error();
      publish({pending:false,notice:'Current chat incoming reads updated; outgoing ownership remains private.'});await refresh();return true;
    }catch{if(live(t,c.key))publish({pending:false,saveUnknown:true,error:'Incoming policy outcome uncertain. Refresh and inspect; no retry.'});return false;}}
  const stops=["focusedStoredSessionId","focusedSessionId","focusedSessionProfile","focusedSessionOwner","profile","connectionId","gateway"].map(k=>host?.state?.[k]).filter(a=>typeof a?.listen==="function").map(a=>a.listen(sync));sync();
  return {refresh,save,create,reconcile,abandon,currentReads,getSnapshot:()=>{sync();return state;},subscribe:f=>{listeners.add(f);return()=>listeners.delete(f);},dispose:()=>{disposed=true;generation++;publish({ownerKey:"",data:null,choices:[],intent:null,created:null,pending:false,ready:false,unconfirmed:false,saveUnknown:false,error:"Private controls disposed",notice:""});stops.forEach(f=>f());listeners.clear();}};
}
function PrivateForm({s,controller}) {
  const [draft,setDraft]=useState(()=>privateClone(s.data.settings)),[project,setProject]=useState(""),[name,setName]=useState("");
  const disabled=s.pending||s.unconfirmed||s.saveUnknown||!s.ready;
  const dirty=privateStable(draft)!==privateStable(s.data.settings);
  const set=(kind,fn)=>setDraft(old=>{const d=privateClone(old);fn(d[kind]);return d;});
  const routeSelect=(label,route,change)=>h("label",{style:{display:'block',marginBlock:'.65rem'}},label,h("select",{"aria-label":label,value:route.provider?JSON.stringify([route.provider,route.model]):"",disabled,onChange:e=>{const [provider,model]=e.target.value?JSON.parse(e.target.value):["",""];change({provider,model});},style:{display:'block',width:'100%',maxWidth:'38rem'}},h('option',{value:""},'Native host default (no global change)'),...s.choices.map(r=>h('option',{key:JSON.stringify([r.provider,r.model]),value:JSON.stringify([r.provider,r.model])},r.provider+' · '+r.model)),route.provider&&!s.choices.some(r=>r.provider===route.provider&&r.model===route.model)&&h('option',{value:JSON.stringify([route.provider,route.model]),disabled:true},'Unavailable: '+route.provider+' · '+route.model)));
  return h('div',null,
    ...[['private_chat','Future private chats'],['private_workspace','Future private workspaces / their new member chats']].map(([kind,title])=>h('fieldset',{key:kind,disabled,style:{marginBlock:'1rem',padding:'1rem'}},h('legend',null,title),
      h('label',null,h('input',{type:'checkbox',checked:draft[kind].workspace_reads,onChange:e=>set(kind,v=>v.workspace_reads=e.target.checked)}),' Read the current workspace pool by default; keep chat-authored notes chat-only'),
      routeSelect('Conversation model',draft[kind].conversation,r=>set(kind,v=>v.conversation=r)),
      h('label',null,'Memory-processing route ',h('select',{'aria-label':'Memory-processing route',value:draft[kind].memory.mode,onChange:e=>set(kind,v=>{v.memory.mode=e.target.value;v.memory.provider='';v.memory.model='';})},h('option',{value:'host'},'Host auxiliary route'),h('option',{value:'separate'},'Separate permitted model'),h('option',{value:'follow_chat'},'Follow current chat (snapshot at draft time)'))),
      draft[kind].memory.mode==='separate'&&routeSelect('Preferred memory model (existing host permission required)',draft[kind].memory,r=>set(kind,v=>Object.assign(v.memory,r))),
      h('label',{style:{display:'block',marginTop:'.7rem'}},h('input',{type:'checkbox',checked:draft[kind].memory.allow_host_fallback,onChange:e=>set(kind,v=>v.memory.allow_host_fallback=e.target.checked)}),' Explicitly allow the host-configured retry/fallback routes for memory processing. Without this, new-container memory generation stays blocked.'))),
    h('button',{disabled:disabled||!dirty,onClick:()=>void controller.save(draft)},'Save future defaults'),
    h('p',null,'Existing containers are not migrated. These defaults apply only to the explicit private-creation actions below. Cloud conversation or memory models receive their selected context. Private is not local-only, provider encryption or a content label. Native conversation retry/fallback settings still apply. Following a chat or selecting a separate memory model requires existing host override permission; the plugin never grants itself one.'),
    h('fieldset',{disabled:true},h('legend',null,'Optional API spending cap — OFF'),h('input',{type:'checkbox',checked:false,readOnly:true}),' Unavailable: this host has no qualified per-attempt fail-closed gate covering native chat, auxiliary retries and fallback. No enabled cap is advertised.'),
    h('h2',null,'Create explicitly private containers'),!s.data.memory_setup&&h('p',{role:'status'},'First use Memory → Create fresh memory store. Creation never initializes it automatically.'),
    h('label',null,'Project placement ',h('select',{'aria-label':'Project placement',disabled,value:project,onChange:e=>setProject(e.target.value)},h('option',{value:''},'Home / no project'),...s.data.projects.map(p=>h('option',{key:p.id,value:p.id},(p.private_workspace?'Private workspace: ':'Project: ')+p.name)))),
    h('p',null,h('button',{disabled:disabled||dirty||!s.data.memory_setup,onClick:()=>void controller.create('private_chat',project,'')},'New private chat'), ' ',h('button',{disabled:disabled||dirty||!s.data.memory_setup||!s.data.projects.some(p=>p.id===project&&p.private_workspace),onClick:()=>void controller.create('workspace_member',project,'')},'New private-workspace member chat')),
    h('label',null,'New private workspace name ',h('input',{disabled,value:name,maxLength:256,onChange:e=>setName(e.target.value)})),h('button',{disabled:disabled||dirty||!s.data.memory_setup||!name||name!==name.trim(),onClick:()=>void controller.create('private_workspace','',name)},'New private workspace'),
    s.data.current_policy?.private&&h('p',null,h('label',null,h('input',{type:'checkbox',disabled:disabled||!s.data.current_policy.workspace_scope_id,checked:s.data.current_policy.workspace_enabled,onChange:e=>void controller.currentReads(e.target.checked)}),' Explicit current-chat choice: read this chat’s current workspace. No outgoing sharing is enabled.')));
}
function PrivatePage({controller}) {
  const s=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  useLayoutEffect(()=>{void controller.refresh();},[controller,s.ownerKey]);
  return h('main',{'aria-label':'Private memory controls',style:{color:'var(--ui-text-primary)',fontSize:'0.9375rem',lineHeight:1.55,padding:'1.25rem',maxWidth:'62rem',overflowWrap:'anywhere'}},
    h('h1',null,'Private memory controls'),h('p',null,'Separate incoming reads, chat-only ownership and future-container defaults. Normal New Chat / New Project behavior stays unchanged. Controls belong to the focused chat’s owning profile/gateway; focus an owned saved chat first.'),
    h('button',{disabled:s.pending,onClick:()=>void controller.refresh()},'Refresh private controls'),
    h('p',{role:'status'},s.pending?'Working…':s.notice),s.error&&h('p',{role:'alert'},s.error),
    s.unconfirmed&&h('section',null,h('p',null,'A creation attempt is unresolved. Inspect native chats/projects before doing anything else; it will not be repeated.'),h('button',{disabled:s.pending,onClick:()=>void controller.reconcile()},'Check prior attempt'),h('button',{disabled:s.pending,onClick:()=>void controller.abandon()},'I inspected the native list — close attempt without retry or deletion')),
    s.created&&h('section',null,h('h2',null,s.created.kind==='private_workspace'?'Private workspace configured':'Private chat configured'),h('code',null,s.created.created_id),s.created.kind!=='private_workspace'&&typeof SDK.host?.openSession==='function'&&h('button',{onClick:()=>void SDK.host.openSession(s.created.created_id)},'Open created chat')),
    s.data&&h(PrivateForm,{key:s.ownerKey+':'+s.data.revision,s,controller}));
}

export default {
  id: "elm",
  name: "Memory",
  defaultEnabled: false,
  register(ctx) {
    const controller = createMemoryController(ctx);
    const privateControls = createPrivateController(ctx);
    ctx.onDispose?.(() => privateControls.dispose());
    const privateRender = () => h(PrivatePage,{controller:privateControls});
    if(typeof ctx.registerSettingsPage === "function"){
      ctx.registerSettingsPage({id:"private-settings",title:"Private memory",icon:"lock",order:20,render:privateRender});
    }else if(SDK.SETTINGS_PLUGINS_AREA){
      ctx.register({id:"private-settings",area:SDK.SETTINGS_PLUGINS_AREA,title:"Private memory",data:{icon:"lock"},render:privateRender});
    }
    const important = createImportantController(ctx), updates = createUpdatesController(ctx);
    ctx.onDispose?.(() => {important.dispose();updates.dispose();});
    const importantRender = () => h(ImportantPage,{controller:important,updates,ctx});
    if(SDK.ROUTES_AREA && SDK.SIDEBAR_NAV_AREA){
      ctx.register({id:"important-page",area:SDK.ROUTES_AREA,data:{path:"/elm-important"},render:importantRender});
      ctx.register({id:"important-nav",area:SDK.SIDEBAR_NAV_AREA,data:{path:"/elm-important",label:"Important results",codicon:"bookmark"}});
    }else ctx.register({id:"important-pane",area:"panes",title:"Important results",data:{placement:"right",width:"380px"},render:importantRender});
    ctx.register({id:"important-count",area:"statusBar.right",order:81,render:()=>h(ImportantChip,{controller:important})});
    if(SDK.TRANSCRIPT_DIRECTIVE_AREA)ctx.register({id:"important-directive",area:SDK.TRANSCRIPT_DIRECTIVE_AREA,
      data:{name:"elm-result",render:({attrs})=>h(ImportantDirective,{attrs,controller:important,ctx})}});
    if(typeof SDK.host?.onEvent === "function"){
      // A turn ending is a refresh opportunity, never a task-completion claim.
      const stop=SDK.host.onEvent('message.complete',event=>{
        const state=SDK.host.state || {}, current=productIdentity(SDK.host);
        // Public gateway events may name the runtime or durable session; absent
        // legacy tags are ambiguous, but explicit foreign ownership is not.
        if (current.error || event?.profile && event.profile !== current.profile ||
            event?.connectionId && event.connectionId !== value(state.connectionId) ||
            event?.session_id && ![current.session,value(state.focusedSessionId)].includes(event.session_id)) return;
        if(!important.getSnapshot().unconfirmed)void important.refresh();
      });
      if(typeof stop === "function")ctx.onDispose?.(stop);
    }
    ctx.onDispose?.(() => controller.dispose());
    const render = () => h(MemoryPage, { controller });
    if (SDK.ROUTES_AREA && SDK.SIDEBAR_NAV_AREA) {
      ctx.register({
        id: "memory-page",
        area: SDK.ROUTES_AREA,
        data: { path: "/elm-memory" },
        render,
      });
      ctx.register({
        id: "memory-nav",
        area: SDK.SIDEBAR_NAV_AREA,
        data: { path: "/elm-memory", label: "Memory", codicon: "book" },
      });
    } else
      ctx.register({
        id: "memory-pane",
        area: "panes",
        title: "Memory",
        data: { placement: "right", width: "380px" },
        render,
      });
    ctx.register({
      id: "memory-boundary",
      area: "statusBar.right",
      order: 80,
      render: () => h(BoundaryChip, { controller }),
    });
    if (typeof ctx.rest === "function") void controller.refresh();
  },
};
