"""`hermes elm` CLI: same trust model as the legacy local_grant helper, simpler use."""
import argparse
import contextlib
import io
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from elm_plugin import cli
from elm_plugin.stock_store import Store

if 'hermes_constants' not in sys.modules:
    try:
        import hermes_constants  # noqa: F401
    except ImportError:
        sys.modules['hermes_constants'] = types.SimpleNamespace(display_hermes_home=lambda: '~/.hermes')


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'db'
        self.store = Store(lambda: sqlite3.connect(path))
        self.parser = argparse.ArgumentParser(prog='hermes elm')
        cli.setup_cli(self.parser, self.store)
    def tearDown(self): self.tmp.cleanup()
    def run_cli(self, *argv, stdin='', tty=False):
        args = self.parser.parse_args(list(argv))
        out = io.StringIO()
        fake_in = io.StringIO(stdin); fake_in.isatty = lambda: tty
        with contextlib.redirect_stdout(out), mock.patch.object(sys, 'stdin', fake_in):
            code = args.func(args)
        return code, out.getvalue()
    def settings(self, session):
        return self.store.authorized_settings(self.store.resolve(session, 'local'))

    def test_grant_with_yes_and_options(self):
        code, out = self.run_cli('grant', 'S1', '--yes', '--project', 'Game', '--hours', '48')
        self.assertEqual(code, 0)
        self.assertIn('project Game', out)
        self.assertEqual(self.settings('S1')['project'], 'Game')

    def test_legacy_flag_name_still_confirms(self):
        self.assertEqual(self.run_cli('grant', 'S1', '--allow-session-clients')[0], 0)

    def test_non_interactive_without_yes_changes_nothing(self):
        code, out = self.run_cli('grant', 'S1')
        self.assertEqual(code, 1)
        self.assertIn('Nothing was changed', out)
        with self.assertRaises(Exception):
            self.settings('S1')

    def test_interactive_confirmation(self):
        self.assertEqual(self.run_cli('grant', 'S1', stdin='n\n', tty=True)[0], 1)
        self.assertEqual(self.run_cli('grant', 'S1', stdin='y\n', tty=True)[0], 0)

    def test_pick_from_recent_chats(self):
        rows = [{'id': 'S9', 'label': 'Plan', 'when': '2026-11-14 01:00', 'source': 'local'},
                {'id': 'S8', 'label': 'Old', 'when': '2026-11-13 01:00', 'source': 'local'}]
        with mock.patch.object(cli, 'recent_sessions', return_value=rows):
            code, out = self.run_cli('grant', stdin='1\ny\n', tty=True)
        self.assertEqual(code, 0)
        self.assertIn('S9', out)
        self.assertEqual(self.settings('S9')['enabled'], 1)

    def test_pick_cancel_and_non_tty(self):
        rows = [{'id': 'S9', 'label': 'Plan', 'when': '', 'source': 'local'}]
        with mock.patch.object(cli, 'recent_sessions', return_value=rows):
            self.assertEqual(self.run_cli('grant', stdin='\n', tty=True)[0], 1)
            self.assertEqual(self.run_cli('grant', '--yes')[0], 1)  # cannot pick without a terminal

    def test_wildcards_refused(self):
        self.assertEqual(self.run_cli('grant', 'S*', '--yes')[0], 2)

    def test_bad_hours_reported_not_raised(self):
        code, out = self.run_cli('grant', 'S1', '--yes', '--hours', '999')
        self.assertEqual(code, 2)
        self.assertIn('invalid_hours', out)

    def test_revoke_keeps_data(self):
        self.run_cli('grant', 'S1', '--yes')
        sid = self.store.resolve('S1', 'local')
        self.store.insert(sid, 'reference', 'kept fact', approved=True)
        self.assertEqual(self.run_cli('revoke', 'S1')[0], 0)
        with self.assertRaises(Exception):
            self.store.resolve('S1', 'local')
        self.run_cli('grant', 'S1', '--yes')
        self.assertEqual(len(self.store.records(self.store.resolve('S1', 'local'), 'kept')), 1)

    def test_session_listing_failure_degrades(self):
        with mock.patch.object(cli, 'recent_sessions', side_effect=RuntimeError('schema')):
            code, out = self.run_cli('grant', stdin='1\n', tty=True)
        self.assertEqual(code, 1)
        self.assertIn('hermes sessions list', out)

    def test_no_subcommand_prints_help(self):
        self.assertEqual(self.run_cli()[0], 0)


if __name__ == '__main__':
    unittest.main()
