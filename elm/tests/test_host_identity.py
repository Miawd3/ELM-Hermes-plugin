"""Real host session/project databases, never the active user's stores."""
import hashlib
import importlib
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from hermes_state import SessionDB
from hermes_cli import projects_db


class HostIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='host-identity-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.db = SessionDB(self.home/'state.db')
        self.addCleanup(self.db.close)
        self.projects = projects_db.connect(self.home/'projects.db')
        self.addCleanup(self.projects.close)

    def resolver(self):
        try:
            module = importlib.import_module('elm_plugin.host_identity')
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.host_identity':
                self.fail('Host-owned memory-scope resolution is not implemented')
            raise
        return module.HostIdentity(self.home)

    def project(self, name):
        project_id = projects_db.create_project(self.projects, name=name)
        return projects_db.get_project(self.projects, project_id)

    def test_recorded_project_beats_active_sidebar_and_misleading_cwd(self):
        expected = self.project('Lantern')
        other = self.project('Harbor')
        self.db.create_session('chat-one', source='desktop', cwd='C:/fictional/Harbor')
        projects_db.set_session_project(self.projects, 'chat-one', expected.id)
        projects_db.set_active(self.projects, other.id)
        result = self.resolver().resolve('chat-one')
        self.assertEqual(result['session_id'], 'chat-one')
        self.assertEqual(result['chat_id'], 'chat-one')
        self.assertEqual(result['project_id'], expected.id)
        self.assertEqual(result['project_name'], 'Lantern')
        self.assertNotEqual(result['project_id'], other.id)


    def test_compressed_continuation_keeps_chat_scope_and_explicit_parent_workspace(self):
        expected = self.project('Lantern')
        misleading = self.project('Harbor')
        self.db.create_session('root-chat', source='desktop')
        projects_db.set_session_project(self.projects, 'root-chat', expected.id, source='manual')
        self.db.end_session('root-chat', 'compression')
        self.db.create_session('continued-chat', source='desktop', parent_session_id='root-chat')
        projects_db.set_session_project(self.projects, 'continued-chat', misleading.id, source='inferred')
        result = self.resolver().resolve('continued-chat')
        self.assertEqual(result['chat_id'], 'root-chat')
        self.assertEqual(result['project_id'], expected.id)


    def test_explicit_home_does_not_infer_workspace_from_directory_or_active_selection(self):
        other = self.project('Harbor')
        self.db.create_session('home-chat', source='desktop', cwd='C:/fictional/Harbor')
        projects_db.set_session_project(self.projects, 'home-chat', None)
        projects_db.set_active(self.projects, other.id)
        self.assertIsNone(self.resolver().resolve('home-chat')['project_id'])

    def test_explicit_home_on_compression_ancestor_beats_inferred_project(self):
        other = self.project('Harbor')
        self.db.create_session('root-chat', source='desktop')
        projects_db.set_session_project(self.projects, 'root-chat', None, source='manual')
        self.db.end_session('root-chat', 'compression')
        self.db.create_session('tip-chat', source='desktop', parent_session_id='root-chat')
        projects_db.set_session_project(self.projects, 'tip-chat', other.id, source='inferred')
        self.assertIsNone(self.resolver().resolve('tip-chat')['project_id'])

    def test_branch_is_a_separate_private_chat_not_parent_memory(self):
        project = self.project('Lantern')
        self.db.create_session('parent-chat', source='desktop')
        projects_db.set_session_project(self.projects, 'parent-chat', project.id)
        self.db.end_session('parent-chat', 'branched')
        self.db.create_session('branch-chat', source='desktop', parent_session_id='parent-chat')
        result = self.resolver().resolve('branch-chat')
        self.assertEqual(result['chat_id'], 'branch-chat')
        self.assertIsNone(result['project_id'])

    def test_old_segment_cannot_inherit_a_future_continuation_grant(self):
        project = self.project('Lantern')
        self.db.create_session('root-chat', source='desktop')
        self.db.end_session('root-chat', 'compression')
        self.db.create_session('tip-chat', source='desktop', parent_session_id='root-chat')
        projects_db.set_session_project(self.projects, 'tip-chat', project.id)
        self.assertIsNone(self.resolver().resolve('root-chat')['project_id'])
        self.assertEqual(self.resolver().resolve('tip-chat')['project_id'], project.id)

    def test_unknown_session_refuses_instead_of_using_current_workspace(self):
        project = self.project('Lantern')
        projects_db.set_active(self.projects, project.id)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            self.resolver().resolve('missing-chat')

    def test_same_session_identifier_in_two_profiles_does_not_share_identity(self):
        self.db.create_session('same-id', source='desktop')
        other_home = self.home/'second-profile'
        other_home.mkdir()
        with closing(SessionDB(other_home/'state.db')) as db:
            db.create_session('same-id', source='desktop')
        module = importlib.import_module('elm_plugin.host_identity')
        first = self.resolver().resolve('same-id')
        second = module.HostIdentity(other_home).resolve('same-id')
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        self.assertNotEqual(first['profile_home'], second['profile_home'])

    def test_read_does_not_mutate_host_database_bytes(self):
        self.db.create_session('chat-one', source='desktop')
        self.db.close()
        self.projects.close()
        paths = (self.home/'state.db', self.home/'projects.db')
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.resolver().resolve('chat-one')
        after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.assertEqual(before, after)

    def test_absent_profile_database_is_not_created(self):
        absent = self.home/'uninitialized'
        module = importlib.import_module('elm_plugin.host_identity')
        with self.assertRaisesRegex(ValueError, 'no stored chat'):
            module.HostIdentity(absent).resolve('missing-chat')
        self.assertFalse(absent.exists())

    def test_archived_workspace_refuses_instead_of_returning_another_workspace(self):
        project = self.project('Lantern')
        self.db.create_session('chat-one', source='desktop')
        projects_db.set_session_project(self.projects, 'chat-one', project.id)
        projects_db.archive_project(self.projects, project.id)
        with self.assertRaisesRegex(ValueError, 'workspace is unavailable'):
            self.resolver().resolve('chat-one')


    def test_workspace_inventory_comes_from_profile_store_and_excludes_archived(self):
        live = self.project('Lantern')
        archived = self.project('Harbor')
        projects_db.archive_project(self.projects, archived.id)
        resolver = self.resolver()
        self.assertTrue(callable(getattr(resolver, 'list_projects', None)), 'Workspace inventory is not implemented')
        self.assertEqual(resolver.list_projects(), [{'id': live.id, 'name': 'Lantern'}])

    def test_reset_and_explicit_forks_of_compressed_parents_do_not_share_chat_scope(self):
        for marker in ('_reset_from', '_branched_from', '_delegate_from'):
            with self.subTest(marker=marker):
                parent = 'parent' + marker
                child = 'child' + marker
                self.db.create_session(parent, source='desktop')
                self.db.end_session(parent, 'compression')
                self.db.create_session(child, source='desktop', parent_session_id=parent,
                                       model_config={marker: parent})
                self.assertEqual(self.resolver().resolve(child)['chat_id'], child)


if __name__ == '__main__':
    unittest.main(verbosity=2)
