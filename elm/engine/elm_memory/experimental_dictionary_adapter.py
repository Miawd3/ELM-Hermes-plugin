"""TEST-ONLY engine bridge. Not a production integration or packaging proposal."""
from . import context as ctx
from . import dictionary_packet as codec


def build_context_packet(task, candidates, budget, *, scope, additional_warnings=None):
    baseline = ctx.build_context_packet(task, candidates, budget, scope=scope,
                                        additional_warnings=additional_warnings)
    packed = codec.build(candidates, baseline, budget, anchor=True)
    if packed['format'] == 'original_fallback':
        return baseline
    normalized = ctx._normalized_candidates(candidates)
    by_locator = {c['locator']: c for c in normalized}
    sources = []
    for record in packed['records']:
        candidate = by_locator[record['source']]
        kind = record['representation']
        sources.append({
            'section_key': candidate['section_key'], 'locator': candidate['locator'],
            **({'memory': candidate['memory']} if candidate.get('memory') else {}),
            'path': candidate['path'], 'heading': candidate['heading_path'],
            'status': candidate['effective_status'], 'authority': candidate['authority'],
            'content_role': candidate['content_role'], 'claim_id': candidate.get('claim_id'),
            'claim_authority': candidate.get('claim_authority'),
            'claim_subject': candidate.get('claim_subject'),
            'claim_predicate': candidate.get('claim_predicate'),
            'claim_object': candidate.get('claim_object'),
            'contradiction': bool(candidate.get('contradiction')),
            'valid_from': candidate.get('valid_from'), 'valid_to': candidate.get('valid_to'),
            'packet_class': candidate['packet_class'],
            'representation_class': (candidate['packet_class'] if kind == 'exact'
                                     else 'source_summary' if kind == 'summary'
                                     else 'relevant_source_manifest'),
            'source_token_estimate': int(candidate.get('token_estimate') or 0),
            'included_exact': kind == 'exact', 'included_summary': kind == 'summary',
        })
    represented = {s['section_key'] for s in sources}
    omitted = [
        {'section_key': c['section_key'], 'locator': c['locator'],
         **({'memory': c['memory']} if c.get('memory') else {}),
         'status': c['effective_status'], 'authority': c['authority'],
         'content_role': c['content_role'], 'claim_id': c.get('claim_id'),
         'claim_authority': c.get('claim_authority'), 'contradiction': bool(c.get('contradiction')),
         'valid_from': c.get('valid_from'), 'valid_to': c.get('valid_to')}
        for c in normalized if c['section_key'] not in represented
    ][:ctx.MAX_OMITTED_LOCATORS]
    exact_count = sum(s['included_exact'] for s in sources)
    summary_count = sum(s['included_summary'] for s in sources)
    omitted_count = len(normalized) - len(sources)
    result = dict(baseline)
    result.update(packet=packed['packet'], estimated_tokens=packed['estimated_tokens'],
                  selected_section_keys=packed['selected_section_keys'], sources=sources,
                  omitted_sources=omitted, omitted_locators_count=len(omitted),
                  omitted_sources_truncated=omitted_count > len(omitted),
                  coverage={'exact_count': exact_count, 'summary_count': summary_count,
                            'manifest_count': len(sources) - exact_count,
                            'omitted_count': omitted_count})
    return result
