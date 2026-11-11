"""Count supported packet records for the recall indicator, never for access control.

Malformed or unknown structured packets get the host's generic indicator. Do
not inspect source text for count-like strings or add rich data to tool output.
"""
import json
import re

_MARKER = '\n\nELM-DICT/1\n'
_SOURCE = re.compile(r'elm://section/section_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
_DEFAULTS = {'status', 'authority', 'content_role', 'packet_class', 'representation', 'memory'}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _packet_source_count(packet, invalid=0):
    """Return a discrete count only for recognized, internally consistent data."""
    if not isinstance(packet, str):
        return invalid
    if _MARKER not in packet:
        if re.search(r'(?m)^ELM-DICT/', packet):
            return invalid  # Unknown version or malformed structured marker.
        # Real legacy metadata is column-zero; quoted source text is prefixed >.
        locators = re.findall(r'(?m)^source: (elm://section/[^\r\n]+)$', packet)
        if (len(locators) > 12 or len(locators) != len(set(locators))
                or any(_SOURCE.fullmatch(value) is None for value in locators)):
            return invalid
        return len(locators)
    try:
        if packet.count(_MARKER) != 1:
            return invalid
        payload = json.loads(packet.split(_MARKER, 1)[1], object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or set(payload) != {'defaults', 'prefixes', 'coverage', 'sources'}:
            return invalid
        defaults, prefixes = payload['defaults'], payload['prefixes']
        coverage, sources = payload['coverage'], payload['sources']
        if (not isinstance(defaults, dict) or set(defaults) - _DEFAULTS
                or any(not isinstance(value, dict if key == 'memory' else str) for key, value in defaults.items())
                or not isinstance(prefixes, dict) or set(prefixes) - {'source', 'path'}
                or any(not isinstance(value, str) for value in prefixes.values())
                or not isinstance(sources, list) or len(sources) > 12
                or not isinstance(coverage, dict) or set(coverage) != {'exact', 'manifest', 'omitted'}
                or any(type(value) is not int or value < 0 for value in coverage.values())):
            return invalid
        locators, kinds = [], []
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get('source'), str):
                return invalid
            record = {**defaults, **source}
            if any(not isinstance(record.get(key), str) for key in
                   ('path', 'heading', 'status', 'authority', 'content_role', 'packet_class', 'representation')):
                return invalid
            locator = prefixes.get('source', '') + record['source']
            kind = record['representation']
            if _SOURCE.fullmatch(locator) is None or kind not in {'exact', 'summary', 'manifest'}:
                return invalid
            if kind in {'exact', 'summary'} and not isinstance(record.get('text'), str):
                return invalid
            if kind == 'manifest' and (type(record.get('source_tokens')) is not int or record['source_tokens'] < 0):
                return invalid
            locators.append(locator)
            kinds.append(kind)
        exact = kinds.count('exact')
        if (len(set(locators)) != len(locators) or coverage['exact'] != exact
                or coverage['manifest'] != len(locators) - exact):
            return invalid
        return len(locators)
    except (ValueError, TypeError, KeyError, RecursionError):
        return invalid


def packet_source_count(packet):
    """Return a discrete count, or the existing generic indicator value zero."""
    return _packet_source_count(packet)


def dictionary_source_count(packet):
    """Return a supported dictionary count, including zero, or None if invalid.

    This validates the existing record/coverage contract, not host-safe encoding
    or header integrity. The delivery adapter checks those separately.
    """
    if not isinstance(packet, str) or _MARKER not in packet:
        return None
    return _packet_source_count(packet, invalid=None)
