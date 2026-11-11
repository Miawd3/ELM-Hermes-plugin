"""Recognized declaration lines must be actually consumed, not merely earlier."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_provider import PLUGIN, engine, note
from test_typed_memory import section_key
sys.path.insert(0, str(PLUGIN/'engine'))
from elm_memory.cli import parse_metadata


def declarations(source, suffix=''):
    values = [('lane','user'), ('kind','hypothesis'), ('basis','inference'),
              ('sensitivity','sensitive_health'), ('source',source)]
    return ''.join(f'Memory {key}{suffix}: {value}\n' for key,value in values)


class DeclarationConsumption(unittest.TestCase):
    def test_declaration_consumption_matrix(self):
        source='elm://section/section_11111111-1111-4111-8111-111111111111'
        ordinary='Title: Invented\nStatus: active\nSummary: Synthetic.\n'
        for suffix in ('', ' ', '\t', '\u00a0'):
            for position in ('first','last','only'):
                for newline in ('\n','\r\n'):
                    with self.subTest(suffix=repr(suffix),position=position,newline=repr(newline)):
                        fields=declarations(source,suffix)
                        header=fields+ordinary if position=='first' else ordinary+fields if position=='last' else fields
                        text=(header+'\n# Invented\n\n## Evidence\n\nSynthetic body.\n').replace('\n',newline)
                        if suffix in ('',' '):
                            meta,_=parse_metadata(text.splitlines(keepends=True))
                            self.assertEqual(5,len([k for k in meta if k.startswith('memory_')]))
                            self.assertEqual('sensitive_health',meta['memory_sensitivity'])
                        else:
                            with self.assertRaises(ValueError):
                                parse_metadata(text.splitlines(keepends=True))

    def test_schema_seven_prefix_legacy_admission_is_invalidated(self):
        # Modeled historical projection. The separate native upgrade acceptance
        # creates a real frozen-v7 index and binding; this model is not that proof.
        with tempfile.TemporaryDirectory(prefix='elm-consumption-v7-',dir=os.environ['TMPDIR']) as temp:
            root=Path(temp)/'store';engine(root,'init','--project','orion')
            source='elm://section/'+section_key(root,'20_projects/orion/ACTIVE_CONTEXT.md','Current state')
            path=root/'20_projects/orion/V7_PREFIX.md'
            body=note('orion','MODELED_V7_PREFIX_PRIVATE')
            path.write_text(body,encoding='utf-8');engine(root,'sync')
            path.write_text(declarations(source,'\t')+body,encoding='utf-8')
            with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                with con:
                    con.execute("UPDATE elm_meta SET value='7' WHERE key='index_schema_version'")
                    con.execute("UPDATE documents SET content_hash=?,mtime_ns=?,size_bytes=? WHERE path='20_projects/orion/V7_PREFIX.md'",
                                (hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_mtime_ns,path.stat().st_size))
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*.md')}
            with self.subTest(boundary='old_projection_refused'):
                self.assertFalse(engine(root,'status','--readiness-only')['healthy'])
            with self.subTest(boundary='reparse_rejected'):
                self.assertTrue(engine(root,'sync')['errors'])
            self.assertEqual(before,{p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*.md')})


if __name__=='__main__':unittest.main(verbosity=2)
