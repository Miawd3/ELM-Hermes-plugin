"""Catalog rule 9 guard: the plugin imports only public Hermes plugin API.

Host-free source test. The workspace, review-UI and skill-update layers needed a patched
Hermes host and were removed in 0.2.0-experimental; this keeps them from coming back.
"""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERMES_TOP = {'agent', 'cli', 'cron', 'gateway', 'hermes_cli', 'hermes_constants', 'hermes_platform',
              'hermes_state', 'hermes_yaml', 'plugins', 'providers', 'tools'}
ALLOWED = {'agent.memory_provider', 'hermes_constants'}
REMOVED = ('product_ui_api', 'workspace_draft_bridge', 'host_identity', 'private_creation', 'result_inbox',
           'scoped_recall', 'workspace_service')


def hermes_imports():
    for path in sorted(ROOT.rglob('*.py')):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in ('tests', 'engine'):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split('.')[0] in HERMES_TOP:
                    yield str(rel), node.lineno, name


class PublicApiOnly(unittest.TestCase):
    def test_only_public_hermes_modules_are_imported(self):
        found = list(hermes_imports())
        self.assertTrue(found, 'scanner found no Hermes imports at all')
        bad = [f'{f}:{line} {name}' for f, line, name in found if name not in ALLOWED]
        self.assertEqual(bad, [])

    def test_removed_host_patch_layers_stay_removed(self):
        for name in REMOVED:
            self.assertFalse((ROOT / 'elm_plugin' / f'{name}.py').exists(), name)
        self.assertFalse((ROOT / 'dashboard').exists())
        self.assertFalse((ROOT / 'desktop').exists())

    def test_register_only_adds_provider_and_starter_skills(self):
        calls = []

        class Ctx:
            def register_memory_provider(self, provider):
                calls.append(('memory', provider.name))

            def register_general_skill(self, name, path, description, frontmatter):
                calls.append(('skill', name))

            def __getattr__(self, attr):
                raise AssertionError(f'register() used ctx.{attr}')

        sys.path.insert(0, str(ROOT.parent))
        try:
            import importlib
            plugin = importlib.import_module(ROOT.name)
            plugin.register(Ctx())
        finally:
            sys.path.remove(str(ROOT.parent))
        self.assertIn(('memory', 'elm-wiki'), calls)
        self.assertEqual(sum(kind == 'skill' for kind, _ in calls), 6)

    def test_own_memory_fence_keeps_packet_bytes(self):
        sys.path.insert(0, str(ROOT))
        try:
            from elm_plugin.measured_context import memory_fence, background_surface
        finally:
            sys.path.remove(str(ROOT))
        packet = 'ELM CONTEXT PACKET\n"quoted" <tag> data'
        self.assertEqual(memory_fence(''), '')
        framed = memory_fence(packet)
        self.assertTrue(framed.startswith('<memory-context>\n') and framed.endswith('\n</memory-context>'))
        self.assertEqual(framed.count(packet), 1)
        self.assertEqual(background_surface(packet), '\n\n' + framed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
