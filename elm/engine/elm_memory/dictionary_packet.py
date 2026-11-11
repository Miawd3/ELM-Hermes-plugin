"""Lossless experimental packet encoding. No storage, search, or provider I/O."""
import copy,json,posixpath,re
from . import context as ctx

MARKER='\n\nELM-DICT/1\n'
SOURCE_PREFIX='elm://section/'
DEFAULT_FIELDS=('status','authority','content_role','packet_class','representation','memory')

def _common_char_prefix(values):
    if not values:return ''
    first,last=min(values),max(values)
    i=0
    while i<min(len(first),len(last)) and first[i]==last[i]:i+=1
    return first[:i]

def _document_identity(c):
    return str(c.get('document_uid') or c.get('document_id') or c['path'])

def make_record(c,kind='exact'):
    r={'source':c['locator'],'path':c['path'],'heading':c['heading_path'],
       'status':c['effective_status'],'authority':c['authority'],'content_role':c['content_role'],
       'packet_class':c['packet_class'],'representation':kind}
    if c.get('memory'):r['memory']=c['memory']
    if kind=='exact':r['text']=str(c.get('text') or '')
    elif kind=='summary':r.update(text=c['document_summary'],summary_origin='canonical_document_metadata')
    else:r['source_tokens']=int(c.get('token_estimate') or 0)
    if c.get('claim_id'):
        r.update(claim_id=c['claim_id'],claim_authority=c.get('claim_authority'),
                 claim={'subject':c.get('claim_subject'),'predicate':c.get('claim_predicate'),'object':c.get('claim_object')})
        for k in ('valid_from','valid_to'):
            if c.get(k):r[k]=c[k]
    if c.get('contradiction'):r['contradiction']=True
    return r

def render(records,header,candidate_count):
    records=copy.deepcopy(records)
    defaults={}
    if records:
        for key in DEFAULT_FIELDS:
            # Require presence and identical JSON values, including nested types:
            # absent is not null, and Python equality conflates false with zero.
            values=[json.dumps(r[key],sort_keys=True,ensure_ascii=False) for r in records if key in r]
            if len(values)==len(records) and all(v==values[0] for v in values):
                defaults[key]=records[0][key]
                for r in records:r.pop(key,None)
    prefixes={}
    if records and all(r['source'].startswith(SOURCE_PREFIX) for r in records):
        prefixes['source']=SOURCE_PREFIX
        for r in records:r['source']=r['source'][len(SOURCE_PREFIX):]
    paths=[r['path'] for r in records]
    prefix=(posixpath.commonpath(paths).rsplit('/',1)[0]+'/' if len(paths)==1 else posixpath.commonpath(paths).rstrip('/')+'/') if paths else ''
    if prefix in {'/','./'}:prefix=''
    if prefix and all(p.startswith(prefix) for p in paths):
        prefixes['path']=prefix
        for r in records:r['path']=r['path'][len(prefix):]
    # Extend the existing prefixes through shared basename/locator characters.
    for key in ('source','path'):
        extra=_common_char_prefix([r[key] for r in records])
        if extra:
            prefixes[key]=prefixes.get(key,'')+extra
            for r in records:r[key]=r[key][len(extra):]
    kinds=[r.get('representation',defaults.get('representation')) for r in records]
    payload={'defaults':defaults,'prefixes':prefixes,
             'coverage':{'exact':kinds.count('exact'),'manifest':len(kinds)-kinds.count('exact'),
                         'omitted':candidate_count-len(records)},'sources':records}
    # The stock host sanitizes memory-context tags and its own System note in
    # opaque provider strings, including occurrences inside JSON string values.
    # JSON Unicode escapes preserve decoded values and protect the serialized
    # payload. This case-insensitive note prefix cannot occur as JSON structure.
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    encoded=encoded.replace('<',r'\u003c')
    encoded=re.sub(r'\[system note:',lambda m:r'\u005b'+m.group()[1:],encoded,flags=re.IGNORECASE)
    return header+MARKER+encoded+'\n'

def decode(packet):
    payload=json.loads(packet.split(MARKER,1)[1]);result=[]
    for stored in payload['sources']:
        r={**payload['defaults'],**stored}
        for key,prefix in payload['prefixes'].items():r[key]=prefix+r[key]
        result.append(r)
    return result

def build(candidates,baseline,budget,anchor=True):
    normalized=ctx._normalized_candidates(candidates);lookup={c['section_key']:c for c in normalized}
    header=baseline['packet'].split('\n\ncoverage:',1)[0]
    records=[]
    summarized=set()
    if anchor:
        for source in baseline['sources']:
            kind='exact' if source['included_exact'] else 'summary' if source['included_summary'] else 'manifest'
            candidate=lookup[source['section_key']]
            records.append(make_record(candidate,kind))
            if kind=='summary':summarized.add(_document_identity(candidate))
    def fits(rs):return ctx.estimate_tokens(render(rs,header,len(normalized)))<=budget
    if not fits(records):
        return {'packet':baseline['packet'],'records':records,'format':'original_fallback',
                'selected_section_keys':baseline['selected_section_keys'],'estimated_tokens':baseline['estimated_tokens']}
    represented={r['source'] for r in records}
    for c in normalized:
        if len(records)>=12:break
        if c['locator'] in represented:continue
        record=make_record(c)
        if fits(records+[record]):records.append(record);represented.add(c['locator'])
    for c in normalized:
        if len(records)>=12:break
        if c['locator'] in represented:continue
        doc=_document_identity(c)
        if isinstance(c.get('document_summary'),str) and c['document_summary'].strip() and doc not in summarized:
            r=make_record(c,'summary')
            if fits(records+[r]):records.append(r);represented.add(c['locator']);summarized.add(doc);continue
        r=make_record(c,'manifest')
        if fits(records+[r]):records.append(r);represented.add(c['locator'])
    packet=render(records,header,len(normalized))
    assert decode(packet)==records
    assert ctx.estimate_tokens(packet)<=budget
    if anchor:
        for old in baseline['sources']:
            r=next(r for r in records if r['source']==old['locator'])
            assert r['path']==old['path'] and r['heading']==old['heading'] and r['authority']==old['authority'] and r['status']==old['status']
            if old['included_exact']:assert r['representation']=='exact'
    return {'packet':packet,'records':records,'format':'dictionary',
            'selected_section_keys':[r['source'][len(SOURCE_PREFIX):] for r in records if r['representation']=='exact'],
            'estimated_tokens':ctx.estimate_tokens(packet)}

def expanded_blocks(records):
    blocks=[]
    for r in records:
        c={**r,'locator':r['source'],'heading_path':r['heading'],'effective_status':r['status'],'token_estimate':r.get('source_tokens',0),'document_summary':r.get('text','')}
        if r.get('claim'):
            c.update({f'claim_{k}':v for k,v in r['claim'].items()})
        f={'exact':ctx._exact_block,'summary':ctx._summary_block,'manifest':ctx._manifest_block}[r['representation']]
        blocks.append(f(c))
    return '\n\n'.join(blocks)
