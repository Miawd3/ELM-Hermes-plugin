"""Conservative recall boundary on real synthetic stores, with stock host imports."""
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_provider as fixtures
from elm_plugin.provider import ElmMemoryProvider
PLUGIN = fixtures.PLUGIN
from elm_plugin.engine import ElmError
from elm_plugin.storage import load_binding


class ExplicitRecallContract(unittest.TestCase):
    setUp = fixtures.ProviderBehavior.setUp
    provider = fixtures.ProviderBehavior.provider
    call = fixtures.ProviderBehavior.call

    def test_default_never_dispatches_or_touches_cache_even_with_stale_payload(self):
        provider = self.provider()
        class Forbidden:
            def __bool__(self):
                raise AssertionError("safe recall inspected cache/worker")
            def __getitem__(self, key):
                raise AssertionError("safe recall read cached payload")
        provider._cache = Forbidden()
        provider._worker = Forbidden()
        try:
            with patch("elm_plugin.provider.run_engine", side_effect=AssertionError("engine dispatch")), \
                    patch("elm_plugin.provider.spawn_context_thread", side_effect=AssertionError("worker dispatch")), \
                    patch("elm_plugin.provider._IndexRevision", side_effect=AssertionError("index access")), \
                    patch.object(provider, "handle_tool_call", side_effect=AssertionError("tool dispatch")), \
                    patch.object(provider, "_clear_cache", side_effect=AssertionError("cache mutation")):
                for query in ("amber canary rollback", "", " ", "--help"):
                    provider.queue_prefetch(query)
                    provider.on_turn_start(1, query)
                    self.assertEqual("", provider.prefetch(query))
                    self.assertEqual("", provider.prefetch(query, session_id="foreign"))
                    self.assertIsNone(provider.recall_status())
        finally:
            provider._cache = provider._worker = None

    def test_missing_legacy_field_defaults_safe_without_rewriting_binding(self):
        self.provider()
        config = self.home / "elm.json"
        value = json.loads(config.read_text())
        value.pop("recall_mode")
        config.write_text(json.dumps(value))
        before = config.read_bytes()
        self.assertEqual("explicit-only", load_binding(self.home).recall_mode)
        fresh = ElmMemoryProvider()
        fresh.initialize("legacy-format", hermes_home=str(self.home))
        self.addCleanup(fresh.shutdown)
        fresh.on_turn_start(1, "amber canary rollback")
        self.assertEqual("", fresh.prefetch("amber canary rollback"))
        self.assertIsNone(fresh._worker)
        self.assertIsNone(fresh._cache)
        self.assertEqual(before, config.read_bytes())
        self.assertIn("signed rollback", self.call(fresh, "elm_context", query="amber canary rollback")["packet"])

    def test_unknown_recall_modes_fail_closed_at_adoption_and_load(self):
        provider = self.provider()
        config = self.home / "elm.json"
        before = config.read_bytes()
        for invalid in ("background", "", None, 1, [], {}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ElmError):
                    provider.save_config({"budget_mode": "legacy-estimate", "root": str(self.root), "project": "orion", "recall_mode": invalid}, str(self.home))
                self.assertEqual(before, config.read_bytes())
                value = json.loads(before)
                value["recall_mode"] = invalid
                config.write_text(json.dumps(value))
                with self.assertRaises(ElmError):
                    load_binding(self.home)
                config.write_bytes(before)

    def test_schema_status_and_cli_report_default_and_legacy(self):
        schema = {v["key"]: v for v in ElmMemoryProvider().get_config_schema()}
        self.assertEqual("explicit-only", schema["recall_mode"]["default"])
        self.assertEqual(["explicit-only", "legacy-background"], schema["recall_mode"]["choices"])
        for mode in ("explicit-only", "legacy-background"):
            provider = self.provider(recall_mode=mode)
            for status in (provider.get_status_config(), self.call(provider, "elm_status")):
                self.assertEqual(mode, status["recall_mode"])
                self.assertEqual(mode == "legacy-background", status["automatic_recall"])
            result = subprocess.run([sys.executable, "-B", str(PLUGIN / "manage.py"), "status", "--hermes-home", str(self.home)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertEqual(mode, json.loads(result.stdout)["recall_mode"])

    def test_cli_rejects_unknown_before_creating_store(self):
        root = self.base / "must-not-exist"
        result = subprocess.run([sys.executable, "-B", str(PLUGIN / "manage.py"), "init", "--hermes-home", str(self.home), "--root", str(root), "--project", "orion", "--recall-mode", "automatic"], capture_output=True, text=True, timeout=30)
        self.assertEqual(2, result.returncode)
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
