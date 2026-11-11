"""Disposable, snapshot-bound ELM generations; authored records are never mutated.

The host supplies a *trusted* approved visible-record snapshot and revalidates its
identity/grants/revisions before publishing. This is not an authentication API.
Only this module's marked cache subtree is owned. Older generations contain
copies until purge; no destructive engine rebuild is used on selected roots.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid

from .engine import ENGINE, ElmError, run_engine
from .workspace_records import recall_eligible as _eligible, recall_records

SCHEMA = 1
CHUNK_CHARS = 4000
MAX_QUERY_CHARS = 2048
PROJECT = 'visible'
PREFIX = f'20_projects/{PROJECT}/records/'
OWNER = 'elm-workspace-derived-index'
ID_RE = r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}'
LOCATOR_RE = r'elm-workspace://(gen_[0-9a-f]{32})/(section_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})'


class IndexError(ValueError):
    def __init__(self, code, message, *, result=None):
        super().__init__(message)
        self.code, self.message, self.result = code, message, result


def _json(value, *, ensure_ascii=False):
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _fail(code, message):
    raise IndexError(code, message)


def _string(value, limit, name):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        _fail('invalid_snapshot', f'Invalid {name}')


def _id(value):
    if not isinstance(value, str) or re.fullmatch(ID_RE, value) is None:
        _fail('invalid_snapshot', 'Invalid scope or record identifier')


def _body(text):
    # Match Python splitlines, as used by ELM, including CR and Unicode line
    # separators. Preserve the original delimiters and indent every parsed line.
    return ''.join('    '+line for line in text.splitlines(keepends=True))


def _projected(text):
    return _body(text).strip()


class WorkspaceIndex:
    def __init__(self, profile_home: Path, cache_root: Path):
        self.home = Path(profile_home).resolve()
        self.cache_root = Path(cache_root)
        if not self.cache_root.is_absolute():
            _fail('invalid_cache', 'An explicit absolute cache root is required')
        self.root = self.cache_root/'elm-workspace-index'
        self.profile = _sha(str(self.home).encode('utf-8'))

    def _safe(self, path):
        # Never follow a replaced subtree or Windows junction during cleanup/read.
        p = Path(path)
        while True:
            if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                _fail('unowned_cache', 'Cache paths may not contain links or junctions')
            if p == p.parent:
                break
            p = p.parent

    def _ensure(self):
        self._safe(self.root)
        marker = self.root/'owner.json'
        expected = dict(owner=OWNER, schema=SCHEMA, profile_sha256=self.profile)
        if self.root.exists():
            try:
                if json.loads(marker.read_text(encoding='utf-8')) != expected:
                    _fail('unowned_cache', 'Cache belongs to another owner or profile')
            except (OSError, ValueError) as exc:
                raise IndexError('unowned_cache', 'Existing cache is not owned; no adoption attempted') from exc
        else:
            self.root.mkdir(parents=True)
            self._atomic(marker, expected)

    @contextmanager
    def _locked(self):
        self._ensure()
        with (self.root/'.index.lock').open('a+b') as stream:
            locked = False
            try:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                raise IndexError('index_busy', 'Another derived-index operation owns the cache') from exc
            try:
                yield
            finally:
                if locked:
                    if os.name == 'nt':
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic(path, data):
        temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.next')
        try:
            with temp.open('w', encoding='utf-8', newline='\n') as stream:
                stream.write(_json(data)+'\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    def _snapshot(self, scope_key, records):
        _id(scope_key)
        if not isinstance(records, list) or len(records) > 10000:
            _fail('invalid_snapshot', 'Snapshot must contain at most 10000 approved records')
        labels = {'explicit_fact': ('explicit_statement','source_document'),
                  'preference': ('explicit_statement',), 'observation': ('direct_observation',),
                  'interpretation': ('inference',), 'summary': ('source_document','inference'),
                  'procedure': ('source_document','inference'), 'reference': ('source_document',)}
        seen = set()
        try:
            copied = json.loads(_json(records))
            for r in copied:
                if not isinstance(r, dict):
                    _fail('invalid_snapshot', 'Records must be objects')
                for field in ('id','scope_id'):
                    _id(r[field])
                if r['id'] in seen or type(r['revision']) is not int or r['revision'] < 1:
                    _fail('invalid_snapshot', 'Duplicate record or invalid revision')
                seen.add(r['id'])
                if (r['state'] != 'approved' or r['domain'] not in ('user','work','reference')
                        or r['kind'] not in labels or r['basis'] not in labels[r['kind']]
                        or type(r['sensitive']) is not bool):
                    _fail('invalid_snapshot', 'Only approved coherent typed records can be indexed')
                if r['domain'] == 'user' and ((r['sensitive'] and r['basis'] != 'explicit_statement')
                        or (r['kind'] == 'explicit_fact' and r['basis'] != 'explicit_statement')):
                    _fail('invalid_snapshot', 'User inferences must not be declared explicit facts or sensitive traits')
                for name, limit in [('title',512),('text',262144),('topic',128)]:
                    _string(r[name],limit,name)
                sources = r['sources']
                if not isinstance(sources,list) or not 1 <= len(sources) <= 64:
                    _fail('invalid_snapshot', 'Nonempty bounded provenance is required')
                for s in sources:
                    if not isinstance(s,dict) or not set(s) <= {'ref','quote','sha256','revision'}:
                        _fail('invalid_snapshot', 'Invalid provenance fields')
                    _string(s['ref'],2048,'source ref')
                    if 'quote' in s: _string(s['quote'],16384,'source quote')
                    if 'sha256' in s and (not isinstance(s['sha256'],str) or re.fullmatch('[0-9a-fA-F]{64}',s['sha256']) is None):
                        _fail('invalid_snapshot','Invalid source digest')
                    if 'revision' in s and (type(s['revision']) is not int or s['revision'] < 1):
                        _fail('invalid_snapshot','Invalid source revision')
                # Cross-scope source bodies are NEVER fetched. Source pointers are
                # opaque labels; only the trusted snapshot decides visibility.
            copied = recall_records(copied)
            copied.sort(key=lambda r:r['id'])
            return copied, _sha(_json(dict(scope_key=scope_key,records=copied)).encode('utf-8'))
        except (KeyError,TypeError,ValueError,UnicodeError) as exc:
            if isinstance(exc,IndexError): raise
            raise IndexError('invalid_snapshot','Malformed typed snapshot') from exc

    @staticmethod
    def _engine_version():
        digest = hashlib.sha256()
        for p in sorted((ENGINE/'elm_memory').glob('*.py')):
            digest.update(p.name.encode()); digest.update(p.read_bytes())
        return digest.hexdigest()

    def _pointer(self, scope_key):
        return self.root/('scope_'+_sha(scope_key.encode('utf-8'))+'.json')

    def _load(self, scope_key):
        path = self._pointer(scope_key)
        if not path.exists(): return None
        try:
            pointer = json.loads(path.read_text(encoding='utf-8'))
            gen = pointer['generation']
            if not isinstance(gen,str) or re.fullmatch('gen_[0-9a-f]{32}',gen) is None:
                raise ValueError('Invalid generation')
            folder = self.root/gen; self._safe(folder)
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            if (manifest['scope_key'] != scope_key or manifest['generation'] != gen
                    or manifest['snapshot_sha256'] != pointer['snapshot_sha256'] or manifest['schema'] != SCHEMA
                    or _sha(_json(dict(scope_key=scope_key,records=manifest['records'])).encode('utf-8')) != pointer['snapshot_sha256']):
                raise ValueError('Generation/pointer/source snapshot mismatch')
            return folder, manifest
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise IndexError('corrupt_index','Selected derived generation is unreadable; authored records are unchanged') from exc

    def _receipt(self, manifest, *, reused=False):
        return dict(generation=manifest['generation'],snapshot_sha256=manifest['snapshot_sha256'],
                    schema=SCHEMA,reused=reused,record_count=len(manifest['records']),
                    section_count=len(manifest['sections']),withheld_record_count=manifest['withheld_record_count'],
                    engine_sha256=manifest['engine_sha256'])

    def _check_files(self, folder, manifest):
        for relative, digest in manifest['projection_hashes'].items():
            path = folder/'root'/relative
            self._safe(path)
            if not path.is_file() or _sha(path.read_bytes()) != digest:
                _fail('index_validation_failed','Projected sources differ from the approved snapshot')

    def _validate_generation(self, folder, manifest):
        self._check_files(folder, manifest)
        status = run_engine(self.home, folder/'root', 'status')
        if not status.get('healthy'):
            raise IndexError('index_validation_failed','ELM generation did not validate',result=status)
        return status

    def _build(self, scope_key, records, force):
        original_count = len(records) if isinstance(records, list) else 0
        records, snapshot = self._snapshot(scope_key, records)
        version = self._engine_version()
        # Explicit repair reconstructs only from the trusted snapshot. The cache
        # ownership/ancestor checks and lock already ran; never read or traverse
        # obsolete selected metadata on this path. Selection stays the last write.
        self._safe(self._pointer(scope_key))
        selected = None if force else self._load(scope_key)
        if selected:
            folder, old = selected
            if old['snapshot_sha256'] == snapshot and old['engine_sha256'] == version:
                self._validate_generation(folder,old)
                return folder, old, True
        gen = 'gen_'+uuid.uuid4().hex
        folder = self.root/gen; folder.mkdir()
        manifest = dict(schema=SCHEMA,generation=gen,scope_key=scope_key,snapshot_sha256=snapshot,
                        engine_sha256=version,records=records,sections={},projection_hashes={},
                        withheld_record_count=original_count-len(records))
        try:
            root = folder/'root'
            initialized = run_engine(self.home,root,'init','--project',PROJECT)
            if initialized['indexed']['errors']:
                _fail('index_validation_failed','ELM initialization reported indexing errors')
            with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                anchor = con.execute("SELECT s.section_key FROM sections s JOIN documents d ON d.id=s.document_id WHERE d.path=? AND s.heading='Current state'",(f'20_projects/{PROJECT}/ACTIVE_CONTEXT.md',)).fetchone()[0]
            out = root/PREFIX; out.mkdir()
            paths = {}
            for r in records:
                if not _eligible(r):
                    manifest['withheld_record_count'] += 1
                    continue
                text = r['text']
                for i,start in enumerate(range(0,len(text),CHUNK_CHARS)):
                    chunk = text[start:start+CHUNK_CHARS]
                    name = _sha(r['id'].encode())+f'_{i}.md'; relative = PREFIX+name
                    title = ' '.join(r['title'].splitlines())+f' [part {i+1}, {_sha(r["id"].encode())[:12]}]'
                    # ASCII JSON escapes every splitlines delimiter in opaque
                    # provenance without changing the original manifest strings.
                    content = (f'Title: {title}\nScope: {r["scope_id"]}\nTags: visible\nStatus: active\n'
                               f'Source refs: {_json(dict(record_id=r["id"],record_revision=r["revision"],source_scope_id=r["scope_id"],sources=r["sources"]), ensure_ascii=True)}\n'
                               'Summary: Approved snapshot projection; source labels are not verification.\n'
                               f'Memory lane: {r["domain"]}\nMemory kind: {r["kind"]}\n'
                               'Memory sensitivity: normal\n'
                               f'Memory source: elm://section/{anchor}\nMemory basis: {r["basis"]}\n\n'
                               '# Content\n\n'+_body(chunk)+'\n')
                    (root/relative).write_text(content,encoding='utf-8',newline='\n')
                    manifest['projection_hashes'][relative] = _sha(content.encode('utf-8'))
                    paths[relative] = dict(record_id=r['id'],start=start,end=start+len(chunk),part=i+1)
            synced = run_engine(self.home,root,'sync')
            if synced['errors']:
                raise IndexError('index_validation_failed','ELM rejected a typed projection',result=synced)
            # Read-only identity binding, never a replacement ranking/index engine.
            with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                for path, binding in paths.items():
                    rows = con.execute('SELECT s.section_key,s.text FROM sections s JOIN documents d ON d.id=s.document_id WHERE d.path=? AND s.heading=?',(path,'Content')).fetchall()
                    r = next(r for r in records if r['id']==binding['record_id'])
                    if len(rows)!=1 or rows[0][1] != _projected(r['text'][binding['start']:binding['end']]):
                        _fail('index_validation_failed','ELM section source equality failed')
                    manifest['sections'][rows[0][0]] = dict(path=path,**binding)
            self._validate_generation(folder,manifest)
            self._atomic(folder/'manifest.json',manifest)
            # Selection is the final write. Failed staging never displaces a
            # valid pointer, even across process reopen or engine upgrades.
            self._atomic(self._pointer(scope_key),dict(generation=gen,snapshot_sha256=snapshot))
            return folder,manifest,False
        except Exception as exc:
            # Keep failed evidence/copies until explicit purge; no success-empty.
            self._atomic(folder/'failure.json',dict(code=getattr(exc,'code','index_build_failed'),
                                                   snapshot_sha256=snapshot))
            if isinstance(exc,IndexError): raise
            raise IndexError('index_build_failed','Staged ELM generation failed; previous selection is unchanged',
                             result=dict(generation=gen,held_path=str(folder))) from exc

    def build(self, scope_key, records, *, force=False):
        if type(force) is not bool: _fail('invalid_request','force must be boolean')
        with self._locked():
            _,manifest,reused = self._build(scope_key,records,force)
            return self._receipt(manifest,reused=reused)

    @staticmethod
    def _intent(record):
        return ['--project',PROJECT,'--memory-lane',record['domain'],'--memory-purpose',
                'communication' if record['domain']=='user' else 'review']

    def _expand(self, folder, manifest, section):
        binding = manifest['sections'].get(section)
        if binding is None: _fail('section_not_visible','Section is not in the current approved generation')
        r = next(r for r in manifest['records'] if r['id']==binding['record_id'])
        raw = run_engine(self.home,folder/'root','read',section,*self._intent(r))
        chunk = r['text'][binding['start']:binding['end']]
        if (raw['path'] != binding['path'] or raw['text'] != _projected(chunk)
                or raw['memory']['lane'] != r['domain'] or raw['memory']['kind'] != r['kind']
                or raw['memory']['basis'] != r['basis']):
            _fail('index_validation_failed','ELM read differs from the approved typed source')
        return dict(record_id=r['id'],record_revision=r['revision'],section=f'elm-workspace://{manifest["generation"]}/{section}',
                    generation=manifest['generation'],snapshot_sha256=manifest['snapshot_sha256'],
                    title=r['title'],text=chunk,domain=r['domain'],kind=r['kind'],basis=r['basis'],
                    sources=deepcopy(r['sources']),source_scope_id=r['scope_id'],topic=r['topic'],
                    authority=raw['authority'],memory=raw['memory'],content_role='untrusted_memory_data',
                    executable=False,part=binding['part'],start=binding['start'],end=binding['end'],
                    total_chars=len(r['text']),representation_class='exact_source_section',
                    record_sections=[dict(section=f'elm-workspace://{manifest["generation"]}/{key}',
                                          part=b['part'],start=b['start'],end=b['end'])
                                     for key,b in sorted(manifest['sections'].items(),key=lambda item:item[1]['start'])
                                     if b['record_id']==r['id']])

    def query(self, scope_key, records, query, *, limit=6):
        _string(query,MAX_QUERY_CHARS,'query')
        if type(limit) is not int or not 1 <= limit <= 12:
            _fail('invalid_request','limit must be 1-12')
        with self._locked():
            folder,manifest,reused = self._build(scope_key,records,False)
            hits = []
            for lane in ('work','reference','user'):
                if not any(_eligible(r) and r['domain']==lane for r in manifest['records']): continue
                raw = run_engine(self.home,folder/'root','search','--project',PROJECT,'--memory-lane',lane,
                                 '--memory-purpose','communication' if lane=='user' else 'review',
                                 '--path-prefix',PREFIX,'--limit',str(limit),'--no-sync','--broad',task=query)
                hits.extend(raw['results'])
            # Scores are the engine's BM25, not a second lexical scorer. All
            # searches use the same immutable ELM database/corpus.
            hits.sort(key=lambda row:(-row['score'],row['section_key']))
            results = [self._expand(folder,manifest,h['section_key']) for h in hits[:limit]]
            return {**self._receipt(manifest,reused=reused),'results':results,'ranking':'ELM search BM25',
                    'max_section_chars':CHUNK_CHARS}

    def read(self, scope_key, records, section):
        match = re.fullmatch(LOCATOR_RE,section) if isinstance(section,str) else None
        if match is None: _fail('section_not_visible','Only exact workspace section locators are accepted')
        with self._locked():
            folder,manifest,_ = self._build(scope_key,records,False)
            if match[1] != manifest['generation']:
                _fail('section_not_visible','Section belongs to another or stale visible generation')
            return self._expand(folder,manifest,match[2])

    def status(self, scope_key, *, records=None):
        _id(scope_key)
        expected = None if records is None else self._snapshot(scope_key, records)[1]
        if not self.root.exists(): return dict(schema=SCHEMA,state='missing',generation=None,held_paths=[])
        with self._locked():
            selected = self._load(scope_key)
            held = [str(p) for p in sorted(self.root.glob('gen_*')) if p.is_dir()]
            if not selected: return dict(schema=SCHEMA,state='missing',generation=None,held_paths=held)
            folder,manifest = selected
            state = 'ready' if manifest['engine_sha256']==self._engine_version() else 'upgrade_required'
            current = expected is not None and manifest['snapshot_sha256'] == expected
            if expected is not None and not current:
                state = 'snapshot_changed'
            self._validate_generation(folder,manifest)
            return {**self._receipt(manifest), 'state':state,'held_paths':held,
                    'copies_retained':True,'snapshot_revalidation_required':expected is None,
                    'snapshot_current':current}

    def purge(self):
        if not self.root.exists(): return dict(removed=True,held_paths=[],copies_retained=False)
        self._ensure()
        held = []
        # Hold the cache lock while removing contents, but not the lock inode.
        with self._locked():
            for child in self.root.iterdir():
                if child.name in ('.index.lock','owner.json'): continue
                try:
                    self._safe(child)
                    if child.is_dir(): shutil.rmtree(child)
                    else: child.unlink()
                except (OSError,IndexError): held.append(str(child))
        # A blocked Windows file is reported, never declared erased. Keep marker
        # and lock for safe subsequent cleanup and cross-process lock identity.
        return dict(removed=not held,held_paths=held,copies_retained=bool(held),
                    metadata_retained=[str(self.root/'owner.json'),str(self.root/'.index.lock')])
