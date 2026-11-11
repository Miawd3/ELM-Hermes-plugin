"""Real public host discovery/lookup; only external completion is faked."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hermes_constants import (get_hermes_home, set_hermes_home_override,
                              reset_hermes_home_override)
from hermes_cli.plugins import (get_plugin_commands, get_plugin_command_handler,
                                get_plugin_manager)
from hermes_cli.plugins_discovery import collect_directory_manifests
from elm_plugin.workspace_service import WorkspaceService

COMMAND = 'elm-workspace-pending-draft'


class DraftBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='draft-bridge-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'profile-a'
        self.home.mkdir()
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        self.manager = get_plugin_manager()
        self.addCleanup(self.manager.unload)
        self.plugin(self.home)
        self.service = WorkspaceService(self.home)
        self.service.setup(confirm=True)
        self.scope = 'workspace:fictional-lantern'
        self.service.store.put_scope(self.scope, 'workspace', 'Fictional Lantern', private=True)
        self.source = self.service.create_record(dict(scope_id=self.scope, title='Brief',
            text='Use indigo banners.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref': 'fictional:brief'}], state='approved'))
        self.service.set_learning(True)
        self.payload = dict(scope_id=self.scope, record_ids=[self.source['id']], kind='summary')
        self.calls = []
        self.complete_patch = patch('agent.auxiliary_client.call_llm', side_effect=self.complete)
        self.complete_patch.start()
        self.addCleanup(self.complete_patch.stop)

    def plugin(self, home, *, kind='standalone', enabled=True, registration=None):
        home.mkdir(parents=True, exist_ok=True)
        token = set_hermes_home_override(home)
        try:
            disabled = sorted({m.name for m in collect_directory_manifests() if m.source == 'bundled'})
        finally:
            reset_hermes_home_override(token)
        (home/'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['elm'] if enabled else [],
            'disabled': disabled, 'isolation': 'in_process'},
            'model': {'provider': 'offline-fixture', 'model': 'fictional-model'}}), encoding='utf-8')
        folder = home/'plugins'/'elm'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'plugin.yaml').write_text('name: elm\nversion: 0.0.0\nkind: '+kind+'\nprovides_tools: []\n', encoding='utf-8')
        (folder/'__init__.py').write_text(registration or (
            'def register(ctx):\n'
            '    from elm_plugin.workspace_draft_bridge import register_workspace_draft_command\n'
            '    register_workspace_draft_command(ctx)\n'
            '    from elm_plugin.provider import ElmMemoryProvider\n'
            '    ctx.register_memory_provider(ElmMemoryProvider())\n'), encoding='utf-8')

    def bridge(self):
        try:
            return importlib.import_module('elm_plugin.workspace_draft_bridge')
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.workspace_draft_bridge':
                self.fail('Host-owned pending-draft command bridge is missing')
            raise

    def complete(self, **kwargs):
        self.calls.append((str(get_hermes_home().resolve()), kwargs))
        return SimpleNamespace(model='fictional-model', provider='offline-fixture',
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
                {'title': 'Banner summary', 'text': 'Use indigo banners.'})))],
            usage=SimpleNamespace(prompt_tokens=50, completion_tokens=20, total_tokens=70))

    def test_captured_handler_cannot_cross_profiles_and_each_profile_has_own_registration(self):
        bridge = self.bridge()
        get_plugin_commands()
        first = get_plugin_command_handler(COMMAND)
        other = Path(self.tmp.name)/'profile-b'
        self.plugin(other)
        second_service = WorkspaceService(other)
        second_service.setup(confirm=True)
        token = set_hermes_home_override(other)
        try:
            other_manager = get_plugin_manager()
            self.addCleanup(other_manager.unload)
            second = get_plugin_command_handler(COMMAND)
            self.assertIsNot(second, first)
            self.assertEqual(json.loads(first(json.dumps(self.payload)))['code'], 'profile_mismatch')
            self.assertEqual(bridge.draft_via_host_command(self.home, self.payload)['code'], 'profile_mismatch')
            result = bridge.draft_via_host_command(other, self.payload)
            self.assertEqual(result['code'], 'learning_disabled')
        finally:
            reset_hermes_home_override(token)
        self.assertIs(get_plugin_command_handler(COMMAND), first)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_pipeline_consent_and_source_refusals_precede_completion(self):
        bridge = self.bridge()
        self.service.set_learning(False)
        self.assertEqual(bridge.draft_via_host_command(self.home, self.payload)['code'], 'learning_disabled')
        self.service.set_learning(True)
        other_scope = 'chat:foreign'
        self.service.store.put_scope(other_scope, 'chat', 'Foreign', private=True)
        result = bridge.draft_via_host_command(self.home, {**self.payload, 'scope_id': other_scope})
        self.assertEqual(result['code'], 'invalid_selection')
        self.assertEqual(self.calls, [])

    def test_explicit_workspace_setup_is_not_implicitly_created(self):
        bridge = self.bridge()
        other = Path(self.tmp.name)/'uninitialized'
        self.plugin(other)
        token = set_hermes_home_override(other)
        try:
            self.addCleanup(get_plugin_manager().unload)
            result = bridge.draft_via_host_command(other, self.payload)
            self.assertEqual(result['code'], 'not_initialized')
            self.assertFalse((other/'elm-workspaces').exists())
        finally:
            reset_hermes_home_override(token)
        self.assertEqual(self.calls, [])

    def test_disabled_general_plugin_does_not_fall_back_to_constructing_llm(self):
        bridge = self.bridge()
        self.plugin(self.home, enabled=False)
        result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertEqual(result['code'], 'draft_bridge_unavailable')
        self.assertIsNone(get_plugin_command_handler(COMMAND))
        self.assertEqual(self.calls, [])

    def test_exclusive_manifest_is_not_loaded_by_general_host_manager(self):
        bridge = self.bridge()
        self.plugin(self.home, kind='exclusive')
        result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertEqual(result['code'], 'draft_bridge_unavailable')
        entries = self.manager.list_plugins()
        entry = next(x for x in entries if x['name'] == 'elm')
        self.assertIn('exclusive', entry['error'])
        self.assertEqual(self.calls, [])

    def test_foreign_handler_is_never_dispatched_or_displaced_by_registration(self):
        from hermes_cli.plugins import PluginContext, PluginManifest
        from elm_plugin.workspace_records import RecordError
        bridge = self.bridge()
        get_plugin_commands()
        foreign_calls = []
        foreign = lambda raw: foreign_calls.append(raw) or '{"ok":true}'
        context = PluginContext(PluginManifest(name='rival', key='rival'), self.manager)
        context.register_command(COMMAND, foreign)
        result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertEqual(result['code'], 'draft_bridge_collision')
        own_context = PluginContext(PluginManifest(name='elm', key='elm'), self.manager)
        with self.assertRaises(RecordError):
            bridge.register_workspace_draft_command(own_context)
        self.assertIs(get_plugin_command_handler(COMMAND), foreign)
        self.assertEqual(foreign_calls, [])
        self.assertEqual(self.calls, [])

    def test_same_owner_metadata_cannot_make_an_unrelated_handler_eligible(self):
        from hermes_cli.plugins import PluginContext, PluginManifest
        bridge = self.bridge()
        get_plugin_commands()
        calls = []
        context = PluginContext(PluginManifest(name='elm', key='elm'), self.manager)
        unrelated = lambda raw: calls.append(raw) or '{"ok":true}'
        context.register_command(COMMAND, unrelated)
        self.assertEqual(bridge.draft_via_host_command(self.home, self.payload)['code'], 'draft_bridge_collision')
        self.assertEqual(calls, [])

    def test_real_host_facade_keeps_override_trust_gate_and_no_tool_registration(self):
        from agent.plugin_llm import PluginLlm, PluginLlmTrustError
        from hermes_cli.plugins import get_plugin_toolsets
        self.bridge()
        handler = get_plugin_command_handler(COMMAND)
        self.assertIsInstance(handler.llm, PluginLlm)
        for args in ({'provider': 'other'}, {'model': 'other'}, {'profile': 'other'}, {'agent_id': 'other'}):
            with self.subTest(args=args), self.assertRaises(PluginLlmTrustError):
                handler.llm.complete(messages=[{'role': 'user', 'content': 'fictional'}], **args)
        self.assertEqual(self.calls, [])
        self.assertNotIn(COMMAND, json.dumps(get_plugin_toolsets()))

    def test_observation_mapping_stays_explicit_and_pending(self):
        result = self.bridge().draft_via_host_command(self.home, {**self.payload, 'kind': 'observation'})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['result']['kind'], 'interpretation')
        self.assertEqual(result['result']['basis'], 'inference')
        self.assertEqual(result['result']['generation_receipt']['requested_kind'], 'observation')
        self.assertEqual(result['result']['state'], 'pending')

    def test_model_error_is_sanitized_and_not_retried(self):
        bridge = self.bridge()
        self.complete_patch.stop()
        with patch('agent.auxiliary_client.call_llm', side_effect=RuntimeError('PRIVATE ERROR')) as boundary:
            result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE ERROR', json.dumps(result))
        self.assertEqual(boundary.call_count, 1)
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_memory_collector_safely_skips_bridge_and_loads_original_candidate_provider(self):
        from plugins.memory import load_memory_provider
        bridge = self.bridge()
        candidate = Path(__file__).resolve().parents[1]
        entrypoint = str(candidate/'__init__.py')
        wrapper = (
            '# register_memory_provider is delegated to the original entrypoint below.\n'
            'def register(ctx):\n'
            '    from elm_plugin.workspace_draft_bridge import register_workspace_draft_command\n'
            '    result = register_workspace_draft_command(ctx)\n'
            '    assert result == {"registered": False, "reason": "context_has_no_llm"}\n'
            '    import importlib.util, sys\n'
            '    name = __name__ + "_candidate"\n'
            f'    spec = importlib.util.spec_from_file_location(name, {entrypoint!r})\n'
            '    module = importlib.util.module_from_spec(spec)\n'
            '    sys.modules[name] = module\n'
            '    spec.loader.exec_module(module)\n'
            '    module.register(ctx)\n')
        self.plugin(self.home, kind='exclusive', registration=wrapper)
        provider = load_memory_provider('elm', register_skills=False)
        self.assertIsNotNone(provider)
        self.assertEqual(type(provider).__name__, 'WorkspaceMemoryProvider')
        self.assertEqual(bridge.draft_via_host_command(self.home, self.payload)['code'], 'draft_bridge_unavailable')
        self.assertEqual(self.calls, [])

    def test_separately_imported_dashboard_namespace_resolves_actual_plugin_handler(self):
        import sys
        bridge = self.bridge()
        candidate_entry = str(Path(__file__).resolve().parents[1]/'__init__.py')
        registration = (
            'def register(ctx):\n'
            '    import importlib, importlib.util, sys\n'
            '    name = __name__ + "_candidate"\n'
            f'    spec = importlib.util.spec_from_file_location(name, {candidate_entry!r})\n'
            '    module = importlib.util.module_from_spec(spec)\n'
            '    sys.modules[name] = module\n'
            '    spec.loader.exec_module(module)\n'
            '    module.register(ctx)\n'
            '    bridge = importlib.import_module(name + ".elm_plugin.workspace_draft_bridge")\n'
            '    bridge.register_workspace_draft_command(ctx)\n')
        self.plugin(self.home, registration=registration)
        get_plugin_commands()
        handler = get_plugin_command_handler(COMMAND)
        self.assertIsNotNone(handler)
        self.assertNotEqual(type(handler).__module__, bridge.__name__)
        # Dashboard loads elm_plugin under a path-qualified independent namespace.
        # Exercise that exact public API loader, not an imagined shared import.
        path = Path(__file__).resolve().parents[1]/'dashboard'/'plugin_api.py'
        name = 'draft_bridge_dashboard_fixture'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        api_bridge = importlib.import_module(module._name + '.workspace_draft_bridge')
        self.assertIsNot(api_bridge, bridge)
        result = api_bridge.draft_via_host_command(self.home, self.payload)
        self.assertTrue(result['ok'], result)
        self.assertIs(get_plugin_command_handler(COMMAND), handler)
        self.assertEqual(self.service.store.get(result['result']['id'])['state'], 'pending')
        self.assertEqual(len(self.calls), 1)

    def test_consent_revocation_during_real_facade_call_discards_output(self):
        bridge = self.bridge()
        self.complete_patch.stop()
        def revoke_then_complete(**kwargs):
            WorkspaceService(self.home).set_learning(False)
            return self.complete(**kwargs)
        with patch('agent.auxiliary_client.call_llm', side_effect=revoke_then_complete):
            result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertFalse(result['ok'], result)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)
        self.assertFalse(self.service.settings()['learning_enabled'])

    def test_two_initialized_profiles_persist_only_their_own_selected_records(self):
        bridge = self.bridge()
        first_result = bridge.draft_via_host_command(self.home, self.payload)
        other = Path(self.tmp.name)/'second-ready-profile'
        self.plugin(other)
        service = WorkspaceService(other)
        service.setup(confirm=True)
        service.store.put_scope(self.scope, 'workspace', 'Separate same-named scope', private=True)
        source = service.create_record(dict(scope_id=self.scope, title='Second profile brief',
            text='Use amber flags.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref': 'fictional:second'}], state='approved'))
        service.set_learning(True)
        token = set_hermes_home_override(other)
        try:
            self.addCleanup(get_plugin_manager().unload)
            result = bridge.draft_via_host_command(other, {**self.payload, 'record_ids': [source['id']]})
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['result']['dependencies'], [{'id': source['id'], 'revision': source['revision']}])
        finally:
            reset_hermes_home_override(token)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][0], str(other.resolve()))
        prompt = json.dumps(self.calls[1][1]['messages'])
        self.assertIn('Use amber flags.', prompt)
        self.assertNotIn('Use indigo banners.', prompt)
        self.assertEqual({r['id'] for r in self.service.store.list_records(self.scope)},
                         {self.source['id'], first_result['result']['id']})
        self.assertEqual({r['id'] for r in service.store.list_records(self.scope)},
                         {source['id'], result['result']['id']})

    def test_only_declared_json_fields_are_accepted_without_caller_authority(self):
        bridge = self.bridge()
        get_plugin_commands()
        handler = get_plugin_command_handler(COMMAND)
        before = self.service.store.status()['revision']
        for extra in ('home', 'root', 'model', 'provider', 'profile', 'approval', 'state', 'enabled', 'session_id'):
            with self.subTest(extra=extra):
                result = bridge.draft_via_host_command(self.home, {**self.payload, extra: 'unauthorized'})
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['code'], 'invalid_draft_request')
        malformed = ['[]', 'null', '{}', '{', '"text"',
            json.dumps({**self.payload, 'scope_id': 1}),
            json.dumps({**self.payload, 'record_ids': 'all'}),
            json.dumps({**self.payload, 'record_ids': [False]}),
            json.dumps({**self.payload, 'kind': 'approve'}),
            json.dumps(self.payload)[:-1] + ',"kind":"procedure"}',
            ' ' * 8193]
        for raw in malformed:
            with self.subTest(raw=raw[:80]):
                result = json.loads(handler(raw))
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['code'], 'invalid_draft_request')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.store.status()['revision'], before)

    def test_public_discovery_and_lookup_save_pending_record_with_real_ctx_llm(self):
        bridge = self.bridge()
        result = bridge.draft_via_host_command(self.home, self.payload)
        self.assertTrue(result['ok'], result)
        handler = get_plugin_command_handler(COMMAND)
        self.assertIsNotNone(handler)
        self.assertEqual(get_plugin_commands()[COMMAND]['plugin_key'], 'elm')
        record = self.service.store.get(result['result']['id'])
        self.assertEqual(record['state'], 'pending')
        self.assertEqual(record['kind'], 'summary')
        self.assertEqual(record['dependencies'], [{'id': self.source['id'], 'revision': self.source['revision']}])
        self.assertEqual(result['result']['generation_receipt']['usage']['total_tokens'], 70)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], str(self.home.resolve()))
        call = self.calls[0][1]
        for key in ('provider', 'model', 'task', 'extra_body', 'route_info'):
            self.assertIsNone(call[key])
        self.assertEqual(call['timeout'], 45.0)
        self.assertEqual(call['max_tokens'], 1024)
        self.assertEqual(WorkspaceService(self.home).store.get(record['id']), record)
