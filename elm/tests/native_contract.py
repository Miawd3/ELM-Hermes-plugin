"""Exercise real stock discovery + MemoryManager, with a disposable profile.

Run using a dependency-prepared stock Hermes interpreter, not bare stdlib Python.
No LLM calls, credentials, permanent installation, or live profile writes.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

PLUGIN = Path(__file__).resolve().parents[1]
STOCK = Path(os.environ.get("HERMES_STOCK_SOURCE", str(PLUGIN.parent / "hermes-stock")))
sys.path.insert(0, str(STOCK))
sys.path.insert(0, str(PLUGIN / "tests"))
from test_provider import engine, note
from packet_contract import packet_locators


def main():
    with tempfile.TemporaryDirectory(prefix="elm-native-", dir=os.environ.get("TMPDIR")) as temporary:
        base = Path(temporary)
        home = base / "profile"
        home.mkdir()
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HERMES_RUNTIME_DIR"] = str(home / "runtime")
        os.environ["HERMES_ENABLE_PROJECT_PLUGINS"] = "0"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        (home / "config.yaml").write_text("memory:\n  provider: elm\nplugins:\n  isolation: in_process\n", encoding="utf-8")
        installed = home / "plugins/elm"
        shutil.copytree(PLUGIN, installed, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "tests"))
        root = base / "memory"
        engine(root, "init", "--project", "orion")
        (root / "20_projects/orion/DECISIONS.md").write_text(
            note("orion", "Orion uses amber canaries and signed rollback."), encoding="utf-8")
        engine(root, "sync")

        from agent.memory_provider import MemoryProvider
        from plugins.memory import find_provider_dir, list_memory_provider_names, load_memory_provider
        from agent.memory_manager import MemoryManager

        assert "elm" in list_memory_provider_names()
        assert find_provider_dir("elm").resolve() == installed.resolve()
        provider = load_memory_provider("elm")
        assert isinstance(provider, MemoryProvider)
        assert provider.name == "elm"
        assert not provider.is_available()
        # Historical background contract is opt-in; default safety has separate tests.
        provider.save_config({"budget_mode": "legacy-estimate", "root": str(root), "project": "orion", "mode": "read-only", "budget": 700,
                              "recall_mode": "legacy-background"}, str(home))
        assert provider.is_available()
        assert provider.get_status_config({})["mode"] == "read-only"
        another = load_memory_provider("elm")
        assert another is not provider

        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id="native-fresh", platform="cli")
        assert manager.get_provider("elm") is provider
        schemas_before = provider.get_tool_schemas()
        assert all(manager.has_tool(name) for name in ("elm_context", "elm_read", "elm_status", "elm_note"))
        output = manager.handle_tool_call("elm_context", {"query": "amber canaries signed rollback"})
        recalled = json.loads(output)
        assert "signed rollback" in recalled["packet"], output
        assert set(recalled) == {"packet", "project", "estimated_tokens", "token_budget"}, recalled
        assert isinstance(recalled["packet"], str), recalled
        locators = packet_locators(recalled["packet"])
        assert locators, output
        locator = locators[0]
        expanded = json.loads(manager.handle_tool_call("elm_read", {"section": locator}))
        bare_expanded = json.loads(manager.handle_tool_call("elm_read", {"section": locator.removeprefix("elm://section/")}))
        assert bare_expanded == expanded
        assert "signed rollback" in expanded.get("text", ""), expanded
        assert expanded["path"].startswith("20_projects/orion/"), expanded
        status = json.loads(manager.handle_tool_call("elm_status", {}))
        assert status["healthy"] and status["project"] == "orion", status
        assert status["mode"] == "read-only" and status["automatic_learning"] is False, status
        assert json.loads(manager.handle_tool_call("elm_context", {"query": "  "}))["error"] == "no_query"
        blocked = json.loads(manager.handle_tool_call("elm_note", {"operation": "remember"}))
        assert blocked["error"] == "write_blocked"
        manager.queue_prefetch_all("amber canaries signed rollback", session_id="native-fresh")
        deadline = time.monotonic() + 8
        prefetch = ""
        while not prefetch and time.monotonic() < deadline:
            time.sleep(0.05)
            prefetch = manager.prefetch_all("amber canaries signed rollback", session_id="native-fresh")
        assert "signed rollback" in prefetch
        assert provider.recall_status().count == len(packet_locators(prefetch))
        assert provider.get_tool_schemas() == schemas_before
        raw = engine(root, "context", "amber canaries signed rollback", "--project", "orion", "--budget", "700", "--no-sync", "--no-trace")
        estimates = {
            "packet_estimated_tokens": raw["estimated_tokens"],
            "tool_delivery_estimated_tokens": (len(output) + 3) // 4,
            "packet_utf8_bytes": len(recalled["packet"].encode("utf-8")),
            "tool_delivery_utf8_bytes": len(output.encode("utf-8")),
            "rich_engine_json_utf8_bytes": len(json.dumps(raw, ensure_ascii=False).encode("utf-8")),
            "fixed_schemas_estimated_tokens": (len(json.dumps(schemas_before)) + 3) // 4,
            "fixed_system_block_estimated_tokens": (len(provider.system_prompt_block()) + 3) // 4,
        }
        manager.shutdown_all()
        another.shutdown()
        print(json.dumps({"native_discovery": "PASS", "real_memory_manager": "PASS",
                          "tool_dispatch": ["elm_context", "elm_read", "elm_status", "elm_note"],
                          "fresh_profile_recall": "PASS", "read_only_gate": "PASS",
                          "background_recall": "PASS", "metrics": estimates}))


if __name__ == "__main__":
    main()
