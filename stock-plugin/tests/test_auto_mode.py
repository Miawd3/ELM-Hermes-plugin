"""Auto mode (`hermes elm auto on`): ELM on for all local chats, shared notes, /elm private."""
import argparse
import gc
import io
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from elm_plugin.memory_provider import ElmMemoryProvider
from elm_plugin.stock_runtime import Runtime
from elm_plugin.stock_store import Store

NOTE = 'The test lighthouse has 4411 steps'
QUESTION = 'How many steps does the test lighthouse have?'


class Ctx:
    def __init__(self): self.surface = 'local'
    def session_surface(self): return self.surface


class AutoModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); path = Path(self.tmp.name) / 'db'
        self.store = Store(lambda: sqlite3.connect(path))
        self.ctx = Ctx()
        self.rt = Runtime(self.ctx, self.store, provider_selected=lambda _sid: False)

    def tearDown(self):
        gc.collect(); self.tmp.cleanup()

    def cmd(self, text, sid='a', platform='local'):
        return self.rt.command(text, session_id=sid, platform=platform)

    def recall(self, sid, platform='local'):
        out = self.rt.before_turn(session_id=sid, user_message=QUESTION) if platform == 'local' else None
        return (out or {}).get('context', '')

    def test_off_by_default(self):
        self.assertEqual(self.store.auto_status(), {'auto_on': False, 'share': True})
        self.assertIn('exact_session_cli_grant_required', self.cmd('status'))
        self.assertIn('hermes elm auto on', self.cmd('status'))

    def test_auto_turns_every_local_chat_on_with_shared_notes(self):
        self.store.set_auto(True)
        status = json.loads(self.cmd('status'))
        self.assertEqual((status['enabled'], status['shared_memory'], status['auto_mode']), (1, True, True))
        self.assertIn('"scope": "user"', self.cmd('save reference ' + NOTE, 'a'))
        self.assertIn('4411', self.recall('b'))  # another chat recalls it
        for sid in ('a', 'b', 'c'):
            self.assertNotIn('error', self.cmd('search lighthouse', sid))

    def test_classic_cli_and_desktop_surfaces_too(self):
        self.store.set_auto(True)
        for platform in ('cli', 'desktop', 'gui', 'tui'):
            self.assertNotIn('error', self.cmd('status', 'x-' + platform, platform))

    def test_never_for_acp_or_messaging(self):
        self.store.set_auto(True)
        for platform in ('acp', 'telegram', 'discord', 'cron', ''):
            self.assertIn('error', self.cmd('status', 'z', platform))
        self.store.set_auto(True)
        provider = ElmMemoryProvider(store_factory=lambda h: self.store)
        provider.initialize('a', hermes_home='/x', platform='acp')
        self.cmd('save reference ' + NOTE, 'a')
        self.assertEqual(provider.prefetch(QUESTION, session_id='a'), '')
        sub = ElmMemoryProvider(store_factory=lambda h: self.store)
        sub.initialize('s', hermes_home='/x', platform='local', agent_context='subagent')
        self.assertEqual(sub.prefetch(QUESTION, session_id='s'), '')

    def test_private_chat_neither_reads_nor_shares(self):
        self.store.set_auto(True)
        self.cmd('save reference ' + NOTE, 'shared-chat')
        self.assertIn('private now', self.cmd('private', 'p'))
        self.assertEqual(self.recall('p'), '')  # does not read shared notes
        saved = json.loads(self.cmd('save reference My private plan is plan B', 'p'))
        self.assertEqual(saved['scope'], 'chat')
        self.assertNotIn('plan B', self.cmd('search private plan', 'other'))  # others cannot read it
        self.assertIn('plan B', self.cmd('search private plan', 'p'))
        self.assertIn('shared memory again', self.cmd('private off', 'p'))
        self.assertIn('4411', self.recall('p'))
        self.assertFalse(json.loads(self.cmd('status', 'p'))['private'] if 'private' in json.loads(self.cmd('status', 'p')) else False)

    def test_private_off_needs_auto_mode_in_local_chats(self):
        self.store.grant_local('g', user=True)
        self.assertIn('private now', self.cmd('private', 'g'))
        self.assertNotIn('error', self.cmd('status', 'g'))  # making a chat private keeps its grant
        self.assertIn('change_permissions_with_local_grant_cli', self.cmd('private off', 'g'))
        self.assertNotIn('error', self.cmd('status', 'g'))
        with self.assertRaises(ValueError):
            self.store.settings(self.store.require_local_grant('g'), {'user_scope': True}, keep_grant=True)

    def test_off_and_on_in_chat(self):
        self.store.set_auto(True)
        self.cmd('save reference ' + NOTE, 'a')
        self.assertIn('off for this chat', self.cmd('off', 'b'))
        self.assertEqual(self.recall('b'), '')
        self.assertIn('enable_this_chat', self.cmd('status', 'b'))  # stays off, auto does not override
        self.assertIn('enabled for this chat', self.cmd('on', 'b'))
        self.assertIn('4411', self.recall('b'))

    def test_auto_off_switches_auto_chats_off_but_keeps_grants(self):
        self.store.set_auto(True)
        self.cmd('status', 'auto-chat')
        self.store.grant_local('granted-chat')
        self.store.set_auto(False)
        self.assertIn('"error"', self.cmd('status', 'auto-chat'))
        self.assertIn('hermes elm auto on', self.cmd('status', 'auto-chat'))
        self.assertEqual(self.recall('auto-chat'), '')
        self.assertNotIn('error', self.cmd('status', 'granted-chat'))
        self.assertIn('exact_session_cli_grant_required', self.cmd('status', 'new-chat'))
        self.ctx.surface = 'cli'
        self.assertIn('error', self.cmd('search x', 'cli-chat', 'cli'))  # classic CLI auto chats too

    def test_on_in_classic_cli_survives_auto_off(self):
        self.store.set_auto(True)
        self.cmd('on', 'k', 'cli')
        self.store.set_auto(False)
        self.assertNotIn('error', self.cmd('status', 'k', 'cli'))

    def test_expired_grant_does_not_block_in_auto_mode(self):
        self.store.grant_local('old')
        with self.store.open() as db:
            db.execute('UPDATE stock_local_grants SET expires=?', (time.time() - 5,))
        db.close()
        self.assertIn('local_grant_expired_or_changed', self.cmd('status', 'old'))
        self.store.set_auto(True)
        self.assertNotIn('error', self.cmd('status', 'old'))

    def test_private_profile_option_keeps_notes_per_chat(self):
        self.store.set_auto(True, share=False)
        self.assertEqual(json.loads(self.cmd('save reference ' + NOTE, 'a'))['scope'], 'chat')
        self.assertEqual(self.recall('b'), '')

    def test_deleting_a_chat_keeps_shared_notes(self):
        self.store.set_auto(True)
        self.cmd('save reference ' + NOTE, 'a')
        self.cmd('private', 'p'); self.cmd('save reference secret plan', 'p')
        self.rt.session_deleted(session_id='a', reason='delete')
        self.rt.session_deleted(session_id='p', reason='delete')
        self.assertIn('4411', self.recall('b'))
        self.assertEqual(self.store.health()['records']['approved'], 1)

    def test_routing_history_follows_sharing(self):
        from elm_plugin.routing import ElmDelegationProvider
        self.store.set_auto(True)
        caller = {'id': 'a'}
        provider = ElmDelegationProvider(runtime=self.rt, session_id=lambda: caller['id'])
        cfg = {'backends': {'elm': {'default': 'quick', 'agents': {
            'quick': {'model': 'f'}, 'coder': {'profile': 'coder'}}}}}
        goal = 'Refactor the payment parser module'
        provider.route_task({'goal': goal, 'agent': 'coder'}, cfg)
        self.rt.subagent_started(parent_session_id='a', child_session_id='c1', child_goal=goal)
        self.rt.subagent_stopped(child_session_id='c1', child_status='completed')
        caller['id'] = 'b'
        self.assertEqual(provider.route_task({'goal': goal}, cfg)['label'], 'ELM: coder (past results)')
        self.cmd('private', 'p'); caller['id'] = 'p'
        self.assertEqual(provider.route_task({'goal': goal}, cfg)['label'], 'ELM: quick (default)')

    def test_cli_auto_command(self):
        from elm_plugin import cli
        def run(*argv):
            parser = argparse.ArgumentParser(); cli.setup_cli(parser, self.store)
            out = io.StringIO()
            with redirect_stdout(out):
                code = parser.parse_args(['auto', *argv]).func(parser.parse_args(['auto', *argv]))
            return code, out.getvalue()
        self.assertIn('Auto mode: off', run()[1])
        code, text = run('on', '--yes')
        self.assertEqual(code, 0); self.assertIn('Auto mode ON', text)
        self.assertEqual(self.store.auto_status(), {'auto_on': True, 'share': True})
        run('on', '--yes', '--private')
        self.assertEqual(self.store.auto_status(), {'auto_on': True, 'share': False})
        self.assertIn('Auto mode off', run('off')[1])
        self.assertFalse(self.store.auto_status()['auto_on'])


if __name__ == '__main__':
    unittest.main()
