"""Behavioral acceptance on synthetic stores with the real vendored engine."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN = Path(__file__).resolve().parents[1]
STOCK = Path(os.environ.get("HERMES_STOCK_SOURCE", str(PLUGIN.parent / "hermes-stock")))
sys.path.insert(0, str(STOCK))
sys.path.insert(0, str(PLUGIN))
from elm_plugin.provider import ElmMemoryProvider
from packet_contract import packet_locators


def engine(root, *args, request=None, task=None):
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR"}}
    env.update(PYTHONPATH=str(PLUGIN / "engine"), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               USERPROFILE=str(root.parent), HOME=str(root.parent))
    command = [sys.executable, "-B", "-m", "elm_memory", *args, "--root", str(root), "--json"]
    if task is not None:
        command.extend(["--", task])
    result = subprocess.run(command,
                            input=json.dumps(request) if request is not None else None,
                            text=True, encoding="utf-8", env=env, cwd=PLUGIN / "engine",
                            capture_output=True, timeout=30)
    if result.returncode:
        raise AssertionError(f"ELM {args}: {result.stdout} {result.stderr}")
    return json.loads(result.stdout)


def note(project, text):
    return (f"Title: {project} release decisions\n"
            f"Scope: {project} only\nTags: {project}, deployment\nStatus: active\n"
            f"Summary: Deployment choices for {project}.\n\n# {project} release decisions\n\n## Deployment\n\n{text}\n")


class ProviderBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="elm-plugin-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "store"
        self.home = self.base / "profile"
        self.home.mkdir()
        engine(self.root, "init", "--project", "orion")
        (self.root / "20_projects/orion/DECISIONS.md").write_text(
            note("orion", "Orion rollout uses the amber canary and requires a signed rollback."), encoding="utf-8")
        other = self.root / "20_projects/lighthouse"
        other.mkdir()
        (other / "DECISIONS.md").write_text(
            note("lighthouse", "LIGHTHOUSE_PRIVATE_DISTRACTOR uses the amber canary without rollback."), encoding="utf-8")
        engine(self.root, "sync")

    def provider(self, mode="read-only", session="fresh", recall_mode="explicit-only"):
        provider = ElmMemoryProvider()
        provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "orion", "mode": mode,
                              "budget": 700, "recall_mode": recall_mode}, str(self.home))
        provider.initialize(session, hermes_home=str(self.home), platform="cli")
        self.addCleanup(provider.shutdown)
        return provider

    def call(self, provider, name, **args):
        return json.loads(provider.handle_tool_call(name, args))

    def test_fresh_session_recalls_only_configured_project_compactly(self):
        first = self.provider(session="first")
        first.shutdown()
        fresh = self.provider(session="second")
        result = self.call(fresh, "elm_context", query="amber canary rollback")
        self.assertIn("signed rollback", result["packet"])
        self.assertNotIn("LIGHTHOUSE_PRIVATE_DISTRACTOR", json.dumps(result))
        self.assertIn("elm://section/", result["packet"])
        self.assertNotIn("sources", result)
        raw = engine(self.root, "context", "amber canary rollback", "--project", "orion",
                     "--budget", "700", "--no-sync", "--no-trace")
        self.assertEqual(raw["packet"], result["packet"])
        self.assertLess(len(json.dumps(result)), len(json.dumps(raw)))
        self.assertLessEqual((len(json.dumps(result)) + 3) // 4, 800)


    def test_read_only_blocks_explicit_learning_without_store_changes(self):
        provider = self.provider()
        before = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file() and ".elm" not in p.parts}
        result = self.call(provider, "elm_note", query="amber canary", operation="remember",
                           subject="Orion", predicate="uses", object="blue canary")
        self.assertEqual("write_blocked", result.get("error"))
        after = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob("*") if p.is_file() and ".elm" not in p.parts}
        self.assertEqual(before, after)


    def candidate(self, object_value="amber canary", submission="11111111-1111-4111-8111-111111111111"):
        return {"submission_id": f"submission_{submission}", "subject": "Orion rollout",
                "predicate": "uses", "object": object_value,
                "valid_from": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rationale": "Synthetic explicit agent observation; unverified.", "source_refs": []}

    def test_proposal_only_persists_reviewable_candidate_but_cannot_activate(self):
        provider = self.provider("proposal-only")
        candidate = self.candidate()
        proposed = self.call(provider, "elm_note", operation="propose", **candidate)
        self.assertEqual("pending", proposed.get("result", {}).get("status"))
        self.assertTrue(proposed["result"]["candidate_untrusted"])
        self.assertTrue(proposed["verification"]["proposal_present"])
        receipt = self.home / "elm/receipts" / (proposed["receipt_id"] + ".json")
        self.assertEqual(proposed, json.loads(receipt.read_text(encoding="utf-8")))
        forbidden = self.call(provider, "elm_note", operation="remember", **candidate)
        self.assertEqual("write_blocked", forbidden["error"])
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        self.assertEqual([], history["claims"])
        self.assertEqual(1, len(history["proposals"]))


    def test_autonomous_learning_replay_duplicate_conflict_and_fresh_recall(self):
        provider = self.provider("autonomous")
        args = self.candidate("violet canary")
        first = self.call(provider, "elm_note", operation="remember", **args)
        self.assertEqual("remembered", first.get("result", {}).get("action"))
        self.assertEqual("agent_curated", first["result"]["authority"])
        self.assertTrue(first["result"]["candidate_activated"])
        self.assertTrue(first["verification"]["claim_present"])
        replay = self.call(provider, "elm_note", operation="remember", **args)
        self.assertTrue(replay["result"]["idempotent_replay"])
        duplicate = self.call(provider, "elm_note", operation="remember", **self.candidate(
            "violet canary", "22222222-2222-4222-8222-222222222222"))
        self.assertEqual("duplicate", duplicate["result"]["action"])
        self.assertFalse(duplicate["result"]["candidate_activated"])
        conflict = self.call(provider, "elm_note", operation="remember", **self.candidate(
            "green canary", "33333333-3333-4333-8333-333333333333"))
        self.assertEqual("conflict_deferred", conflict["result"]["action"])
        self.assertFalse(conflict["result"]["candidate_activated"])
        self.assertTrue(conflict["verification"]["proposal_present"])
        self.assertEqual(first["result"]["claim_id"], conflict["result"]["existing_claim_id"])
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        self.assertEqual(1, len(history["claims"]))
        self.assertEqual(3, len(history["proposals"]))
        fresh = self.provider("autonomous", session="new-session")
        recall = self.call(fresh, "elm_context", query="Orion violet canary")
        self.assertIn("violet canary", recall["packet"])
        self.assertIn("agent_curated", recall["packet"])
        self.assertNotIn("green canary", recall["packet"])


    def test_model_cannot_override_scope_or_dispatch_unknown_tool(self):
        provider = self.provider()
        bad = self.call(provider, "elm_context", query="amber canary", project="lighthouse")
        self.assertEqual("invalid_arguments", bad.get("error"))
        unknown = self.call(provider, "elm_approve", query="amber canary")
        self.assertEqual("unknown_tool", unknown.get("error"))
        root_override = self.call(provider, "elm_context", query="amber", root=str(self.base))
        self.assertEqual("invalid_arguments", root_override.get("error"))

    def test_leading_dash_context_queries_are_literal_data(self):
        provider = self.provider()
        before = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file()}
        for query in ("--no-sync", "--help", "-x", "--project lighthouse", "--budget=1", "--root=ignored"):
            with self.subTest(query=query):
                result = self.call(provider, "elm_context", query=query)
                self.assertIn("packet", result)
                raw = engine(self.root, "context", "--project", "orion", "--budget", "700",
                             "--no-sync", "--no-trace", task=query)
                self.assertEqual(raw["packet"], result["packet"])
                self.assertNotIn("LIGHTHOUSE_PRIVATE_DISTRACTOR", result["packet"])
        after = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_leading_dash_note_values_are_literal_data_during_readback(self):
        provider = self.provider("autonomous")
        for subject, predicate, submission in (
                (" --help ", "uses", "44444444-4444-4444-8444-444444444444"),
                ("Orion option fixture", " --no-sync ", "55555555-5555-4555-8555-555555555555")):
            with self.subTest(subject=subject, predicate=predicate):
                candidate = self.candidate("--root is literal object text", submission)
                candidate.update(subject=subject, predicate=predicate)
                saved = self.call(provider, "elm_note", operation="remember", **candidate)
                self.assertEqual("remembered", saved.get("result", {}).get("action"))
                history = engine(self.root, "history", "--project", "orion", "--no-sync")
                claim = next(c for c in history["claims"]
                             if c["claim_id"] == saved["result"]["claim_id"])
                self.assertEqual(subject.strip(), claim["subject"])
                self.assertEqual(predicate.strip(), claim["predicate"])
                self.assertTrue(saved["verification"].get("proposal_present"), saved["verification"])
                self.assertTrue(saved["verification"].get("claim_present"), saved["verification"])
                receipt = self.home / "elm/receipts" / (saved["receipt_id"] + ".json")
                self.assertEqual(saved, json.loads(receipt.read_text(encoding="utf-8")))

    def test_literal_context_keeps_scrubbed_engine_boundary(self):
        from unittest.mock import patch
        provider = self.provider()
        real_run = subprocess.run
        calls = []
        def observe(command, **kwargs):
            calls.append((command, kwargs))
            return real_run(command, **kwargs)
        poison = {key: "SYNTHETIC_MUST_NOT_REACH_ENGINE" for key in
                  ("OPENAI_API_KEY", "ELM_ROOT", "HERMES_HOME", "PYTHONHOME", "PYTHONPATH")}
        query = "--project lighthouse"
        with patch.dict(os.environ, poison), patch("elm_plugin.engine.subprocess.run", side_effect=observe):
            result = self.call(provider, "elm_context", query=query)
        self.assertIn("packet", result)
        self.assertNotIn("LIGHTHOUSE_PRIVATE_DISTRACTOR", result["packet"])
        self.assertEqual(1, len(calls))
        command, options = calls[0]
        self.assertEqual([sys.executable, "-B", "-s", "-S", "-m", "elm_memory"], command[:6])
        self.assertEqual(["--", query], command[-2:])
        self.assertIn("--require-current-projection", command[:-2])
        self.assertIn("--expected-root-identity-sha256", command[:-2])
        self.assertEqual(str(self.root), command[command.index("--root") + 1])
        self.assertEqual("orion", command[command.index("--project") + 1])
        self.assertIs(False, options["shell"])
        self.assertEqual(20, options["timeout"])
        child_env = options["env"]
        self.assertFalse(set(child_env) - {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
                                          "PYTHONPATH", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE",
                                          "HOME", "USERPROFILE"})
        self.assertNotIn("SYNTHETIC_MUST_NOT_REACH_ENGINE", child_env.values())
        self.assertEqual(str(PLUGIN / "engine"), child_env["PYTHONPATH"])
        self.assertEqual(str(self.home), child_env["HOME"])

    def test_lost_write_reply_reports_unknown_outcome_not_saved(self):
        from unittest.mock import patch
        provider = self.provider("autonomous")
        real_run = subprocess.run
        def lose_committed_reply(command, **kwargs):
            completed = real_run(command, **kwargs)
            if command[6] == "remember-submit":
                self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
                raise subprocess.TimeoutExpired(command, 20)
            return completed
        with patch("elm_plugin.engine.subprocess.run", side_effect=lose_committed_reply):
            result = self.call(provider, "elm_note", operation="remember", **self.candidate())
        self.assertEqual("engine_timeout", result.get("error"))
        self.assertIn("may have committed", result["message"])
        self.assertNotIn("receipt_id", result)
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        self.assertEqual(1, len(history["claims"]))
        self.assertEqual("amber canary", history["claims"][0]["object"])


    def test_provider_instance_cannot_rebind_to_another_home(self):
        provider = self.provider()
        other_home = self.base / "other-profile"
        other_home.mkdir()
        provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "orion", "mode": "autonomous"}, str(other_home))
        with self.assertRaisesRegex(ValueError, "already bound"):
            provider.initialize("other", hermes_home=str(other_home))
        wrong_caller = json.loads(provider.handle_tool_call("elm_context", {"query": "amber"},
                                                           hermes_home=str(other_home)))
        self.assertEqual("profile_mismatch", wrong_caller.get("error"))


    def test_exact_expansion_preserves_source_and_authority_without_duplicate_body(self):
        provider = self.provider()
        raw = engine(self.root, "context", "amber canary rollback", "--project", "orion",
                     "--budget", "700", "--no-sync", "--no-trace")
        source = next(item for item in raw["sources"] if item["path"].endswith("DECISIONS.md"))
        expanded = self.call(provider, "elm_read", section=source["locator"])
        exact = engine(self.root, "read", source["section_key"], "--project", "orion")
        self.assertEqual(exact["text"], expanded.get("text"))
        for key in ("section_key", "path", "authority", "content_role", "claim_authority", "claim_id", "start_line", "end_line"):
            self.assertEqual(exact.get(key), expanded.get(key))
        self.assertEqual(1, json.dumps(expanded).count("signed rollback"))
        denied = self.call(provider, "elm_read", section="../../other-profile/secrets.md")
        self.assertEqual("invalid_arguments", denied.get("error"))
        status = self.call(provider, "elm_status")
        self.assertTrue(status.get("healthy"))
        self.assertEqual("read-only", status["mode"])
        self.assertFalse(status["automatic_learning"])


    def test_background_recall_is_lean_and_sync_turn_stores_no_raw_chat(self):
        import time
        provider = self.provider(recall_mode="legacy-background")  # Explicit historical-mode regression.
        prompt = provider.system_prompt_block()
        start = time.monotonic()
        self.assertEqual("", provider.prefetch("amber canary rollback", session_id="fresh"))
        self.assertLess(time.monotonic() - start, 0.2)
        deadline = time.monotonic() + 6
        packet = ""
        while not packet and time.monotonic() < deadline:
            time.sleep(0.05)
            packet = provider.prefetch("amber canary rollback", session_id="fresh")
        self.assertIn("signed rollback", packet)
        # Check the actual outer tool envelope, not a key inside the new packet.
        delivered = self.call(provider, "elm_context", query="amber canary rollback")
        self.assertEqual(set(delivered), {"packet", "project", "estimated_tokens", "token_budget"})
        self.assertEqual(delivered["packet"], packet)
        self.assertIsInstance(delivered["packet"], str)
        self.assertEqual(provider.recall_status().count, len(packet_locators(packet)))
        self.assertIsNotNone(provider.recall_status())
        self.assertEqual("", provider.prefetch("completely different task", session_id="fresh"))
        self.assertIsNone(provider.recall_status())
        provider.sync_turn("RAW_CHAT_DO_NOT_STORE", "SECRET_ASSISTANT_DO_NOT_STORE", messages=[{"role": "user", "content": "RAW"}])
        self.assertEqual(prompt, provider.system_prompt_block())
        stored = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in self.home.rglob("*") if p.is_file())
        self.assertNotIn("RAW_CHAT_DO_NOT_STORE", stored)
        self.assertNotIn("SECRET_ASSISTANT_DO_NOT_STORE", stored)


    def test_empty_queries_never_fall_back_or_raise(self):
        provider = self.provider()
        for query in ("", " ", "\n\t"):
            result = self.call(provider, "elm_context", query=query)
            self.assertEqual("no_query", result.get("error"))
            self.assertEqual("", provider.prefetch(query))


    def test_non_primary_context_cannot_write_even_in_autonomous_profile(self):
        setup = ElmMemoryProvider()
        setup.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "orion", "mode": "autonomous"}, str(self.home))
        for context in ("subagent", "cron", "flush", "unknown", None):
            with self.subTest(context=context):
                child = ElmMemoryProvider()
                child.initialize("child", hermes_home=str(self.home), agent_context=context)
                self.addCleanup(child.shutdown)
                result = self.call(child, "elm_note", operation="remember", **self.candidate())
                self.assertEqual("write_blocked", result.get("error"))

    def test_stale_root_identity_changes_and_missing_root_fail_closed(self):
        provider = self.provider("autonomous")
        source = self.root / "20_projects/orion/DECISIONS.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nUnindexed change.\n", encoding="utf-8")
        result = self.call(provider, "elm_context", query="canary")
        self.assertEqual("engine_refused", result.get("error"))
        result = self.call(provider, "elm_note", operation="remember", **self.candidate())
        self.assertEqual("store_not_ready", result.get("error"))
        identity = self.root / "00_registry/ELM_ROOT_ID.json"
        value = json.loads(identity.read_text(encoding="utf-8"))
        value["creator"] = "different-owner"
        identity.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual("root_identity_changed", self.call(provider, "elm_context", query="canary")["error"])
        self.assertEqual("root_identity_changed", self.call(provider, "elm_note", operation="remember", **self.candidate())["error"])
        identity.unlink()
        self.assertEqual("root_identity_unavailable", self.call(provider, "elm_context", query="canary")["error"])

    def test_read_delivery_does_not_modify_canonical_sources_index_or_engine(self):
        provider = self.provider()
        def snapshot(root):
            return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob("*") if p.is_file()}
        before, vendor = snapshot(self.root), snapshot(PLUGIN / "engine")
        self.call(provider, "elm_context", query="canary")
        self.call(provider, "elm_status")
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(vendor, snapshot(PLUGIN / "engine"))
        self.assertFalse((self.root / ".elm/traces").exists())

    def test_unknown_adoption_project_and_missing_explicit_home_are_rejected(self):
        provider = ElmMemoryProvider()
        with self.assertRaises(ValueError):
            provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "nonexistent"}, str(self.home))
        self.assertFalse((self.home / "elm.json").exists())
        with self.assertRaises(KeyError):
            provider.initialize("no-home")


    def test_note_readback_matches_canonical_ids_after_text_normalization(self):
        provider = self.provider("autonomous")
        candidate = self.candidate(" padded canary ")
        candidate.update(subject=" Orion rollout ", predicate=" uses ")
        saved = self.call(provider, "elm_note", operation="remember", **candidate)
        self.assertEqual("remembered", saved.get("result", {}).get("action"))
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        claim = next(c for c in history["claims"] if c["claim_id"] == saved["result"]["claim_id"])
        proposal = next(p for p in history["proposals"]
                        if p["proposal_id"] == saved["result"]["proposal_id"])
        self.assertEqual("Orion rollout", claim["subject"])
        self.assertEqual("uses", claim["predicate"])
        self.assertEqual("padded canary", claim["object"])
        self.assertEqual(claim["proposal_id"], proposal["proposal_id"])
        self.assertTrue(saved["verification"]["proposal_present"])
        self.assertTrue(saved["verification"]["claim_present"])
        receipt = self.home / "elm/receipts" / (saved["receipt_id"] + ".json")
        self.assertEqual(saved, json.loads(receipt.read_text(encoding="utf-8")))

    def test_note_receipt_keeps_admitted_session_through_readback_switch(self):
        from unittest.mock import patch
        from elm_plugin.provider import run_engine as real_run
        provider = self.provider("autonomous", session="session-A")
        switched = []
        def switch_during_readback(*args, **kwargs):
            if args[2] == "history":
                provider.on_session_switch("session-B")
                switched.append(True)
            return real_run(*args, **kwargs)
        with patch("elm_plugin.provider.run_engine", side_effect=switch_during_readback):
            saved = self.call(provider, "elm_note", operation="remember", **self.candidate())
        self.assertEqual([True], switched)
        self.assertEqual("remembered", saved.get("result", {}).get("action"))
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        self.assertIn(saved["result"]["claim_id"], [c["claim_id"] for c in history["claims"]])
        self.assertTrue(saved["verification"]["claim_present"])
        receipt = self.home / "elm/receipts" / (saved["receipt_id"] + ".json")
        persisted = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual("session-A", saved["session_id"])
        self.assertEqual("session-A", persisted["session_id"])
        self.assertEqual(saved, persisted)

    def test_receipt_keeps_committed_disposition_if_readback_fails(self):
        from unittest.mock import patch
        from elm_plugin.engine import ElmError
        from elm_plugin.provider import run_engine as real_run
        provider = self.provider("autonomous")
        def fail_readback(*args, **kwargs):
            if args[2] == "history":
                raise ElmError("fixture_io_failure", "Injected readback failure")
            return real_run(*args, **kwargs)
        with patch("elm_plugin.provider.run_engine", side_effect=fail_readback):
            result = self.call(provider, "elm_note", operation="remember", **self.candidate())
        self.assertEqual("remembered", result.get("result", {}).get("action"))
        self.assertEqual("fixture_io_failure", result["verification"]["readback_error"])
        self.assertTrue(result["result"]["canonical_committed"])
        self.assertTrue(result["receipt_persisted"])


    def test_invalid_persisted_scope_mode_is_not_a_write_grant(self):
        provider = self.provider()
        config = self.home / "elm.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["mode"] = "typo-autonomy"
        config.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            ElmMemoryProvider().initialize("bad-config", hermes_home=str(self.home))
        with self.assertRaises(ValueError):
            provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "../lighthouse"}, str(self.home))


    def test_native_setup_fields_and_operator_init_status_roundtrip(self):
        fields = {field["key"] for field in ElmMemoryProvider().get_config_schema()}
        self.assertEqual({"root", "project", "mode", "budget", "recall_mode", "budget_mode", "tokenizer", "tokenizer_vocab"}, fields)
        other_home = self.base / "new-operator-profile"
        other_root = self.base / "new-operator-store"
        def manage(*args):
            result = subprocess.run([sys.executable, "-B", str(PLUGIN / "manage.py"), *args,
                                     "--hermes-home", str(other_home)],
                                    capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            return json.loads(result.stdout)
        initialized = manage("init", "--budget-mode", "legacy-estimate", "--root", str(other_root), "--project", "demo")
        self.assertEqual("read-only", initialized["mode"])
        status = manage("status")
        self.assertTrue(status["healthy"])
        self.assertEqual("demo", status["project"])


    def wait_packet(self, provider, query, expected):
        import time
        deadline = time.monotonic() + 8
        packet = ""
        while time.monotonic() < deadline:
            packet = provider.prefetch(query)
            if expected in packet:
                return packet
            time.sleep(0.05)
        self.fail(f"Background recall did not contain {expected!r}: {packet}")

    def test_background_cache_rejects_commits_held_in_wal(self):
        import sqlite3
        provider = self.provider(recall_mode="legacy-background")  # Explicit historical-mode regression.
        query = "canary rollback"
        self.wait_packet(provider, query, "signed rollback")
        index = self.root / ".elm/index.sqlite"
        held = sqlite3.connect(index)
        self.addCleanup(held.close)
        held.execute("SELECT count(*) FROM documents").fetchone()
        before = index.stat().st_mtime_ns, index.stat().st_size
        source = self.root / "20_projects/orion/DECISIONS.md"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "signed rollback", "WAL_NEW_ROLLBACK"), encoding="utf-8")
        engine(self.root, "sync")
        self.assertEqual(before, (index.stat().st_mtime_ns, index.stat().st_size))
        self.assertTrue(index.with_name("index.sqlite-wal").is_file())
        self.assertTrue(self.call(provider, "elm_status")["healthy"])
        fresh = self.call(provider, "elm_context", query=query)
        self.assertIn("WAL_NEW_ROLLBACK", fresh["packet"])
        self.assertNotIn("signed rollback", provider.prefetch(query))
        self.wait_packet(provider, query, "WAL_NEW_ROLLBACK")

    def test_background_cache_rejects_time_only_claim_expiry(self):
        from datetime import timedelta
        provider = self.provider("autonomous", recall_mode="legacy-background")  # Explicit historical-mode regression.
        candidate = self.candidate("EXPIRING_SYNTHETIC_LEASE")
        saved = self.call(provider, "elm_note", operation="remember", **candidate)
        self.assertEqual("remembered", saved.get("result", {}).get("action"))
        claim_id = saved["result"]["claim_id"]
        history = engine(self.root, "history", "--project", "orion", "--no-sync")
        claim = next(c for c in history["claims"] if c["claim_id"] == claim_id)
        query = "Orion EXPIRING_SYNTHETIC_LEASE"
        boundary = datetime.fromisoformat(claim["valid_to"])
        with self.controlled_clock(provider, boundary - timedelta(seconds=1)) as clock:
            self.wait_packet(provider, query, claim_id)
            index = self.root / ".elm/index.sqlite"
            before = hashlib.sha256(index.read_bytes()).hexdigest()
            clock[0] = boundary + timedelta(microseconds=1)
            self.assertEqual(before, hashlib.sha256(index.read_bytes()).hexdigest())
            self.assertTrue(self.call(provider, "elm_status")["healthy"])
            self.assertNotIn(claim_id, self.call(provider, "elm_context", query=query)["packet"])
            self.assertNotIn(claim_id, provider.prefetch(query))
            self.assertIsNone(provider.recall_status())
            self.assertNotIn(claim_id, self.wait_packet(provider, query, "ELM CONTEXT PACKET"))

    def test_background_cache_refreshes_when_future_claim_becomes_valid(self):
        from datetime import timedelta
        provider = self.provider(recall_mode="legacy-background")  # Explicit historical-mode regression.
        boundary = datetime.now(timezone.utc) + timedelta(days=1)
        # Autonomous future notes intentionally defer. Use the real operator path
        # to create an accepted but not-yet-current canonical claim.
        proposed = engine(self.root, "propose", "--project", "orion",
                          "--actor", "synthetic-operator", "--subject", "Orion rollout",
                          "--predicate", "uses", "--object", "FUTURE_SYNTHETIC_LEASE",
                          "--valid-from", boundary.isoformat(timespec="microseconds"))
        accepted = engine(self.root, "accept", proposed["proposal_id"],
                          "--actor", "synthetic-operator", "--authority", "user_ratified")
        claim_id = accepted["claim_id"]
        query = "Orion FUTURE_SYNTHETIC_LEASE"
        with self.controlled_clock(provider, boundary - timedelta(seconds=1)) as clock:
            self.assertNotIn(claim_id, self.wait_packet(provider, query, "ELM CONTEXT PACKET"))
            index = self.root / ".elm/index.sqlite"
            before = hashlib.sha256(index.read_bytes()).hexdigest()
            clock[0] = boundary + timedelta(microseconds=1)
            self.assertEqual(before, hashlib.sha256(index.read_bytes()).hexdigest())
            self.assertTrue(self.call(provider, "elm_status")["healthy"])
            self.assertIn(claim_id, self.call(provider, "elm_context", query=query)["packet"])
            self.wait_packet(provider, query, claim_id)

    @contextmanager
    def controlled_clock(self, provider, moment):
        """Freeze only time; each read still runs the real vendored CLI process.

        Test-only bootstrap replaces the module launcher, not engine responses or
        source files. Preserve the actual subprocess arguments/environment and
        finish background work before unpatching either side's clock.
        """
        from unittest.mock import patch
        clock = [moment]
        real_run = subprocess.run

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock[0].astimezone(tz) if tz is not None else clock[0].replace(tzinfo=None)

        def run_at_clock(command, *args, **kwargs):
            command = list(command)
            i = command.index("-m")
            self.assertEqual("elm_memory", command[i + 1])
            bootstrap = ("from datetime import datetime as D\n"
                         "from elm_memory import cli, context, governance\n"
                         f"stamp = {clock[0].isoformat()!r}\n"
                         "class Clock(D):\n"
                         " @classmethod\n"
                         " def now(cls, tz=None):\n"
                         "  value = D.fromisoformat(stamp)\n"
                         "  return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)\n"
                         "for module in (cli, context, governance): module.datetime = Clock\n"
                         "raise SystemExit(cli.main())\n")
            command[i:i + 2] = ["-c", bootstrap]
            return real_run(command, *args, **kwargs)

        with patch("elm_plugin.provider.datetime", Clock, create=True), \
                patch("elm_plugin.engine.subprocess.run", side_effect=run_at_clock):
            try:
                yield clock
            finally:
                provider.shutdown()

    def test_background_cache_does_not_block_operator_rebuild(self):
        provider = self.provider(recall_mode="legacy-background")  # Explicit historical-mode regression.
        query = "canary rollback"
        self.wait_packet(provider, query, "signed rollback")
        source = self.root / "20_projects/orion/DECISIONS.md"
        source.write_text(source.read_text(encoding="utf-8").replace(
            "signed rollback", "REBUILT_SYNTHETIC_ROLLBACK"), encoding="utf-8")
        engine(self.root, "rebuild")
        self.assertTrue(self.call(provider, "elm_status")["healthy"])
        self.assertNotIn("signed rollback", provider.prefetch(query))
        self.wait_packet(provider, query, "REBUILT_SYNTHETIC_ROLLBACK")

    def test_background_cache_is_invalidated_after_operator_sync(self):
        import time
        provider = self.provider(recall_mode="legacy-background")  # Explicit historical-mode regression.
        def wait_packet():
            deadline = time.monotonic() + 6
            packet = ""
            while not packet and time.monotonic() < deadline:
                packet = provider.prefetch("canary rollback")
                time.sleep(0.05)
            return packet
        self.assertIn("signed rollback", wait_packet())
        source = self.root / "20_projects/orion/DECISIONS.md"
        source.write_text(source.read_text(encoding="utf-8").replace("signed rollback", "staged rollback"), encoding="utf-8")
        engine(self.root, "sync")
        self.assertNotIn("signed rollback", provider.prefetch("canary rollback"))
        self.assertIn("staged rollback", wait_packet())


if __name__ == "__main__":
    unittest.main(verbosity=2)
