"""Isolated synthetic host API probes, not real-host acceptance."""
import ast
import contextlib
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from elm_plugin.host_identity import HostIdentity, IdentityError
from elm_plugin.host_requirements import inspect_host, main


class HostRequirementTests(unittest.TestCase):
    def modules(self, resolver=None):
        projects = types.ModuleType('hermes_cli.projects_db')
        projects.get_project = lambda *args: None
        if resolver is not None:
            projects.resolve_session_project = resolver
        cli = types.ModuleType('hermes_cli')
        cli.projects_db = projects
        state = types.ModuleType('hermes_state')
        state.SessionDB = lambda *args, **kwargs: self.fail('Must not open a host database')
        return {'hermes_cli': cli, 'hermes_cli.projects_db': projects, 'hermes_state': state}

    def test_absent_resolver_refuses_before_database_read(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('sys.modules', self.modules()):
            root = Path(tmp) / 'uncreated'
            with self.assertRaises(IdentityError) as exc:
                HostIdentity(root).resolve('chat')
            self.assertEqual(exc.exception.code, 'host_api_unsupported')
            self.assertFalse(root.exists())

    def test_missing_host_module_refuses(self):
        with patch.dict('sys.modules', {'hermes_state': None}):
            with self.assertRaises(IdentityError) as exc:
                HostIdentity('/nonexistent').resolve('chat')
            self.assertEqual(exc.exception.code, 'host_api_unsupported')

    def test_http_mapping_unit(self):
        # Execute only the actual response-mapping function. This is not a
        # FastAPI transport/integration test and needs no external host imports.
        path = Path(__file__).parents[1] / 'elm_plugin/workspace_api.py'
        tree = ast.parse(path.read_text())
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'failure')
        class Response:
            def __init__(self, body, status_code):
                self.body, self.status_code = body, status_code
        scope = {'JSONResponse': Response}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), scope)
        response = scope['failure'](IdentityError('host_api_unsupported', 'Unavailable'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.body['code'], 'host_api_unsupported')

    def test_noncallable_resolver_refuses(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('sys.modules', self.modules(True)):
            with self.assertRaises(IdentityError) as exc:
                HostIdentity(tmp).resolve('chat')
            self.assertEqual(exc.exception.code, 'host_api_unsupported')

    def test_invalid_session_preserves_validation(self):
        with patch.dict('sys.modules', self.modules()):
            with self.assertRaises(IdentityError) as exc:
                HostIdentity('/nonexistent').resolve('')
            self.assertEqual(exc.exception.code, 'invalid_session')

    def test_presence_does_not_claim_compatibility(self):
        with patch.dict('sys.modules', self.modules(lambda *a: None)):
            report = inspect_host()
        self.assertEqual(report['status'], 'required_symbols_present_unverified')
        self.assertIn('ownership_semantics', report['not_verified'])

    def test_absent_symbol_diagnostic(self):
        with patch.dict('sys.modules', self.modules()):
            report = inspect_host()
        self.assertEqual(report['status'], 'workspace_host_unsupported')

    def test_import_failure_is_redacted(self):
        with patch('elm_plugin.host_requirements.importlib.import_module', side_effect=RuntimeError('secret/path')):
            report = inspect_host()
        self.assertNotIn('secret/path', json.dumps(report))
        self.assertEqual(report['status'], 'workspace_host_unsupported')

    def test_cli_exit_is_machine_readable(self):
        output = io.StringIO()
        with patch.dict('sys.modules', self.modules()), contextlib.redirect_stdout(output):
            status = main()
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())['schema_version'], 1)

    def test_readonly_existing_files_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('sys.modules', self.modules()):
            root = Path(tmp)
            (root / 'state.db').write_bytes(b'not a database')
            with self.assertRaises(IdentityError):
                HostIdentity(root).resolve('chat')
            self.assertEqual((root/'state.db').read_bytes(), b'not a database')
            self.assertEqual([p.name for p in root.iterdir()], ['state.db'])


if __name__ == '__main__':
    unittest.main()
