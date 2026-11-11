"""Synthetic core + actual Hermes MemoryManager/provider-hook tests; no model calls."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT.parents[1]
HOST = Path(os.environ.get("HERMES_STOCK_SOURCE", str(ROOT.parent / "integration_elm_20261106/isolated_runtime/hermes-stock"))).resolve()
sys.path[:0] = [str(PLUGIN), str(HOST)]
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused, CONFIG_NAME
from elm_plugin.provider import ElmMemoryProvider


def no_sockets(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        raise RuntimeError("Network disabled in synthetic test")
sys.addaudithook(no_sockets)


@dataclass
class UnitBinding:
    root_id: str = "root_12345678-1234-4234-8234-123456789012"
    project: str = "orion"

    def check_identity(self):
        return None


def config(home, binding, **overrides):
    value = {"format_version": 1, "enabled": True, "root_id": binding.root_id,
             "project": binding.project, **overrides}
    (home / CONFIG_NAME).write_text(json.dumps(value), encoding="utf-8")


def pair(number=1, user="I prefer concise answers.", assistant="I will keep that in mind."):
    return [{"message_uid": f"u{number}", "role": "user", "content": user},
            {"message_uid": f"a{number}", "role": "assistant", "content": assistant}]


class CaptureCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="elm-episode-core-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.binding = UnitBinding()
        self.now = 1000.0

    def start(self, **values):
        config(self.home, self.binding, **values)
        capture, reason = EpisodeCapture.from_profile(self.home, self.binding, "primary", clock=lambda: self.now)
        self.assertEqual(reason, "ready")
        return capture

    def append(self, capture, rows=None, session="s1", **kwargs):
        rows = rows or pair()
        return capture.append_turn(session, rows[-2]["content"], rows[-1]["content"], messages=rows, **kwargs)

    def contents(self, capture, table="messages"):
        with closing(sqlite3.connect(capture.path)) as con:
            return con.execute(f"SELECT * FROM {table}").fetchall()

    def test_disabled_and_non_primary_create_no_buffer(self):
        capture, reason = EpisodeCapture.from_profile(self.home, self.binding, "primary")
        self.assertIsNone(capture)
        self.assertEqual(reason, "disabled")
        config(self.home, self.binding)
        for context in ("subagent", "cron", "flush", "unknown"):
            self.assertIsNone(EpisodeCapture.from_profile(self.home, self.binding, context)[0])
        self.assertFalse((self.home / "elm").exists())

    def test_durable_restart_and_global_uid_dedup(self):
        first = self.start()
        self.assertEqual(self.append(first)["captured_messages"], 2)
        second, _ = EpisodeCapture.from_profile(self.home, self.binding, "primary", clock=lambda: self.now)
        self.assertEqual(self.append(second, session="branch")["status"], "duplicate")
        self.assertEqual(len(self.contents(second)), 2)
        self.assertEqual(len(self.contents(second, "episodes")), 1)

    def test_identical_text_different_ids_is_distinct(self):
        capture = self.start()
        self.append(capture, pair(1))
        self.append(capture, pair(2))
        self.assertEqual(len(self.contents(capture)), 4)

    def test_scope_config_mismatch_refused(self):
        config(self.home, self.binding, project="different")
        with self.assertRaisesRegex(CaptureRefused, "scope_mismatch"):
            EpisodeCapture.from_profile(self.home, self.binding, "primary")
        self.assertFalse((self.home / "elm").exists())

    def test_distinct_profiles_and_roots_do_not_share(self):
        first = self.start()
        self.append(first)
        other_home = self.home / "other"
        other_home.mkdir()
        config(other_home, self.binding)
        second, _ = EpisodeCapture.from_profile(other_home, self.binding, "primary", clock=lambda: self.now)
        self.assertNotEqual(first.scope, second.scope)
        self.assertEqual(second.status()["active_messages"], 0)
        alternate = UnitBinding(root_id="root_22345678-1234-4234-8234-123456789012")
        config(self.home, alternate)
        third, _ = EpisodeCapture.from_profile(self.home, alternate, "primary", clock=lambda: self.now)
        self.assertNotEqual(first.scope, third.scope)
        self.assertEqual(third.status()["active_messages"], 0)

    def test_config_withdrawal_stops_existing_instance(self):
        capture = self.start()
        config(self.home, self.binding, enabled=False)
        with self.assertRaisesRegex(CaptureRefused, "config_changed"):
            self.append(capture)
        self.assertEqual(len(self.contents(capture)), 0)

    def test_fields_allowlisted_and_secret_patterns_redacted(self):
        capture = self.start()
        rows = pair(user="password=synthetic_secret Please use concise answers.")
        rows[0].update(api_content="INJECTED_SYSTEM_MARKER", secret="METADATA_SECRET_MARKER",
                       reasoning="REASONING_MARKER", image={"data": "IMAGE_MARKER"})
        rows[1].update(reasoning_content="HIDDEN_REASONING_MARKER", tool_results="TOOL_DUMP_MARKER")
        self.append(capture, rows)
        stored = json.dumps(self.contents(capture))
        self.assertIn("[redacted]", stored)
        for marker in ("synthetic_secret", "INJECTED_SYSTEM_MARKER", "METADATA_SECRET_MARKER",
                       "REASONING_MARKER", "IMAGE_MARKER", "HIDDEN_REASONING_MARKER", "TOOL_DUMP_MARKER"):
            self.assertNotIn(marker, stored)

    def test_media_hidden_scaffolding_and_data_use_refused(self):
        capture = self.start()
        variants = [
            {"content": "data:image/png;base64,SYNTHETIC"},
            {"content": [{"type": "text", "text": "not plain"}]},
            {"display_kind": "hidden"}, {"display_kind": "internal_notification"},
            {"display_kind": "process_complete"}, {"display_kind": "async_delegation_complete"},
            {"_compressed_summary": True},
            {"display_metadata": {"inflight_task_restatement": True}},
            {"display_metadata": {"compaction_inflight_task_restatement": True}},
            {"display_metadata": {"withheld_prompt": "PRIVATE"}},
            {"display_metadata": {"data_use": ["restricted"]}},
            {"data_use": ["restricted"]}, {"_absorbed_message_uids": ["old"]},
        ]
        for update in variants:
            with self.subTest(update=list(update)):
                rows = pair()
                rows[0].update(update)
                with self.assertRaises(CaptureRefused):
                    self.append(capture, rows)
        self.assertEqual(len(self.contents(capture)), 0)

    def test_missing_uid_or_unwitnessed_source_refused(self):
        capture = self.start()
        rows = pair()
        rows[0].pop("message_uid")
        with self.assertRaisesRegex(CaptureRefused, "stable_message_uid"):
            self.append(capture, rows)
        with self.assertRaisesRegex(CaptureRefused, "source_text_mismatch"):
            capture.append_turn("s1", "different", "reply", messages=pair())
        with self.assertRaisesRegex(CaptureRefused, "stable_messages_required"):
            capture.append_turn("s1", "text", "reply")

    def test_restricted_tool_turn_is_not_captured_via_assistant(self):
        capture = self.start()
        rows = pair()
        rows.insert(1, {"role": "tool", "content": "RESTRICTED_TOOL_MARKER", "data_use": ["restricted"]})
        with self.assertRaisesRegex(CaptureRefused, "restricted_turn_data_use"):
            capture.append_turn("s1", rows[0]["content"], rows[-1]["content"], messages=rows)
        self.assertEqual(len(self.contents(capture)), 0)

    def test_earlier_restricted_context_blocks_later_paraphrase(self):
        capture = self.start()
        rows = [{"role": "tool", "content": "EARLIER_RESTRICTED_MARKER", "data_use": ["restricted"]}] + pair()
        with self.assertRaisesRegex(CaptureRefused, "restricted_turn_data_use"):
            capture.append_turn("s1", rows[-2]["content"], rows[-1]["content"], messages=rows)
        self.assertEqual(len(self.contents(capture)), 0)

    def test_changed_uid_content_is_not_silently_overwritten(self):
        capture = self.start()
        self.append(capture)
        with self.assertRaisesRegex(CaptureRefused, "identity_conflict"):
            self.append(capture, pair(user="I prefer long answers."))
        self.assertIn("concise", json.dumps(self.contents(capture)))
        self.assertNotIn("long answers", json.dumps(self.contents(capture)))

    def test_author_identity_and_bot_rejection(self):
        capture = self.start()
        self.append(capture, turn_author={"id": "human1", "name": "NOT_STORED_NAME", "is_bot": False})
        stored = json.dumps(self.contents(capture))
        self.assertIn("human1", stored)
        self.assertNotIn("NOT_STORED_NAME", stored)
        with self.assertRaisesRegex(CaptureRefused, "identity_conflict"):
            self.append(capture, turn_author={"id": "human2", "is_bot": False})
        with self.assertRaisesRegex(CaptureRefused, "bot_author"):
            self.append(capture, pair(2), turn_author={"id": "bot", "is_bot": True})

    def test_count_and_ledger_caps_do_not_partially_commit(self):
        capture = self.start(max_messages=2, max_seen_ids=2)
        self.append(capture)
        with self.assertRaisesRegex(CaptureRefused, "capacity_reached"):
            self.append(capture, pair(2))
        self.assertEqual(len(self.contents(capture)), 2)
        self.now += 259201
        with self.assertRaisesRegex(CaptureRefused, "capacity_reached"):
            self.append(capture, pair(3))
        self.assertEqual(len(self.contents(capture, "seen")), 2)

    def test_text_byte_cap_rejects_whole_pair(self):
        capture = self.start(max_text_bytes=256)
        with self.assertRaisesRegex(CaptureRefused, "capacity_reached"):
            self.append(capture, pair(user="é" * 80, assistant="é" * 80))
        self.assertEqual(len(self.contents(capture)), 0)

    def test_expiry_and_replay_do_not_resurrect(self):
        capture = self.start(retention_seconds=60)
        self.append(capture)
        self.now += 61
        capture.seal("s1", "session_end")
        self.assertEqual(len(self.contents(capture)), 0)
        self.assertEqual(len(self.contents(capture, "seen")), 2)
        self.assertEqual(self.append(capture)["status"], "duplicate")
        self.assertEqual(capture.status()["active_messages"], 0)

    def test_thresholds_and_explicit_boundaries(self):
        capture = self.start(episode_turns=1)
        self.assertTrue(self.append(capture)["episode_sealed"])
        self.assertEqual(self.contents(capture, "episodes")[0][4], "size_boundary")
        capture.seal("s1", "pre_compress")
        self.assertEqual(capture.status()["active_messages"], 2)


class RealProviderHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="elm-episode-native-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home, self.root = self.base / "profile", self.base / "store"
        self.home.mkdir()
        keys = ("HOME", "HERMES_HOME", "HERMES_RUNTIME_DIR", "HERMES_ENABLE_PROJECT_PLUGINS")
        old = {key: os.environ.get(key) for key in keys}
        def restore():
            for key, value in old.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value
        self.addCleanup(restore)
        os.environ.update(HOME=str(self.base), HERMES_HOME=str(self.home),
                          HERMES_RUNTIME_DIR=str(self.base / "runtime"), HERMES_ENABLE_PROJECT_PLUGINS="0")
        (self.home / "config.yaml").write_text("memory:\n  provider: elm\nplugins:\n  isolation: in_process\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.base),
               "USERPROFILE": str(self.base),
               "PYTHONPATH": str(PLUGIN / "engine"), "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-B", "-m", "elm_memory", "init", "--root", str(self.root),
                                 "--project", "orion", "--json"], env=env, cwd=PLUGIN / "engine",
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def provider(self, enable=True, context="primary"):
        provider = ElmMemoryProvider()
        provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "orion", "mode": "read-only", "budget": 700}, str(self.home))
        from elm_plugin.storage import load_binding
        if enable: config(self.home, load_binding(self.home), episode_turns=2)
        from agent.memory_manager import MemoryManager
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all("session1", hermes_home=str(self.home), platform="cli", agent_context=context)
        self.assertIs(manager.get_provider("elm"), provider)
        self.addCleanup(manager.shutdown_all)
        return provider, manager

    def test_real_manager_async_capture_seal_restart_and_readonly_store(self):
        provider, manager = self.provider()
        before = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(("-shm", "-wal"))}
        rows = pair()
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session1", messages=rows,
                         turn_author={"id": "verified-user", "is_bot": False})
        self.assertTrue(manager.flush_pending(timeout=10))
        self.assertEqual(provider.episode_capture_status()["active_messages"], 2)
        manager.on_pre_compress(rows)
        self.assertFalse(manager.supports_pre_compress_checkpoint())
        manager.commit_session_boundary_async(rows, new_session_id="session2")
        self.assertTrue(manager.flush_pending(timeout=10))
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session2", messages=rows,
                         turn_author={"id": "verified-user", "is_bot": False})
        self.assertTrue(manager.flush_pending(timeout=10))
        self.assertEqual(provider.episode_capture_status()["active_messages"], 2)
        after = {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(("-shm", "-wal"))}
        self.assertEqual(before, after)
        status = json.loads(manager.handle_tool_call("elm_status", {}))
        self.assertFalse(status["automatic_learning"])
        self.assertFalse(status["episode_capture"]["retrieval_enabled"])

    def test_disabled_provider_does_not_capture(self):
        provider, manager = self.provider(enable=False)
        rows = pair()
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session1", messages=rows)
        self.assertTrue(manager.flush_pending(timeout=10))
        self.assertFalse(provider.episode_capture_status()["enabled"])
        self.assertFalse((self.home / "elm/episodes").exists())

    def test_live_config_revocation_and_wrong_session_refused(self):
        provider, manager = self.provider()
        rows = pair()
        provider.sync_turn(rows[0]["content"], rows[1]["content"], session_id="wrong", messages=rows)
        self.assertEqual(provider._episode_last["status"], "capture_session_mismatch_or_closed")
        config(self.home, provider._binding, enabled=False)
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session1", messages=rows)
        self.assertTrue(manager.flush_pending(timeout=10))
        self.assertEqual(provider._episode_last["status"], "capture_config_changed")

    def test_non_primary_cannot_capture(self):
        provider, manager = self.provider(context="subagent")
        rows = pair()
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session1", messages=rows)
        self.assertTrue(manager.flush_pending(timeout=10))
        self.assertEqual(provider.episode_capture_status()["status"], "non_primary_context")
        self.assertFalse((self.home / "elm/episodes").exists())

    def test_uninitialized_shutdown_is_safe(self):
        provider = ElmMemoryProvider()
        provider.shutdown()
        provider.shutdown()
        self.assertIsNone(provider._episode_capture)


if __name__ == "__main__":
    unittest.main(verbosity=2)
