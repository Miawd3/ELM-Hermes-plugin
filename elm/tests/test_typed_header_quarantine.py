"""Reserved declaration recognition and v6 projection invalidation regressions."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_provider import engine, note, PLUGIN
from test_typed_memory import typed_note, section_key
sys.path.insert(0, str(PLUGIN / 'engine'))
from elm_memory.cli import parse_metadata


class TypedHeaderQuarantine(unittest.TestCase):
    def test_reserved_header_spellings_cannot_become_unclassified(self):
        valid = typed_note('orion', 'INVENTED_DECLARATION_ONLY')
        variants = {
            'hash_nonheading': valid.replace('Memory lane:', '#not-a-heading\nMemory lane:'),
            'indented': valid.replace('\nMemory ', '\n Memory '),
            'unknown_identifier': note('orion', 'INVENTED_DECLARATION_ONLY').replace(
                '\n\n#', '\nMemory owner_id: anyone\n\n#', 1),
            'tabbed_namespace': valid.replace('Memory lane:', 'Memory\tlane:'),
        }
        for label, text in variants.items():
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    parse_metadata(text.splitlines(keepends=True))

    def test_real_heading_still_bounds_declarations_not_literal_body_examples(self):
        text = note('orion', 'Literal example follows.\nMemory owner_id: a quoted property example.')
        meta, _ = parse_metadata(text.splitlines(keepends=True))
        self.assertFalse(any(k.startswith('memory_') for k in meta))
        ordinary = note('orion', 'Ordinary legacy work evidence.').replace(
            '\n\n#', '\n#not-a-heading\n\n#', 1)
        meta, _ = parse_metadata(ordinary.splitlines(keepends=True))
        self.assertEqual('active', meta['status'])
        self.assertFalse(any(k.startswith('memory_') for k in meta))

    def test_schema_six_legacy_projection_is_reparsed_not_blessed_after_parser_fix(self):
        # Model the old v6 projection defect, without shipping the vulnerable
        # parser: same canonical body/hash, no typed properties, previous schema.
        # Separate owner acceptance also upgrades a real frozen-v6-created store.
        with tempfile.TemporaryDirectory(prefix='elm-header-v6-', dir=os.environ['TMPDIR']) as temp:
            root = Path(temp) / 'store'
            engine(root, 'init', '--project', 'orion')
            source = 'elm://section/' + section_key(root, '20_projects/orion/ACTIVE_CONTEXT.md', 'Current state')
            path = root / '20_projects/orion/MODELED_V6.md'
            path.write_text(note('orion', 'MODELED_V6_HIDDEN_MARKER'), encoding='utf-8')
            engine(root, 'sync')
            malformed = typed_note('orion', 'MODELED_V6_HIDDEN_MARKER', source=source,
                                   kind='hypothesis', sensitivity='sensitive_health').replace(
                                       'Memory lane:', '#not-a-heading\nMemory lane:')
            path.write_text(malformed, encoding='utf-8')
            with closing(sqlite3.connect(root / '.elm/index.sqlite')) as con:
                with con:
                    con.execute("UPDATE elm_meta SET value='6' WHERE key='index_schema_version'")
                    con.execute("UPDATE documents SET content_hash=?,mtime_ns=?,size_bytes=? WHERE path='20_projects/orion/MODELED_V6.md'",
                                (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns, path.stat().st_size))
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*.md')}
            with self.subTest(boundary='old_projection_refused'):
                self.assertFalse(engine(root, 'status', '--readiness-only')['healthy'])
            with self.subTest(boundary='sync_reparses_unchanged_hash'):
                self.assertTrue(engine(root, 'sync')['errors'])
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*.md')})


if __name__ == '__main__':
    unittest.main(verbosity=2)
