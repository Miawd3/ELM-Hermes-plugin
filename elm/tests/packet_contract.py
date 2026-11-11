"""Test-side locator reconstruction; never a stock-host decoder claim."""
import json
import re

MARKER = '\n\nELM-DICT/1\n'
SOURCE = re.compile(r'elm://section/section_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def packet_locators(packet):
    if MARKER not in packet:
        return re.findall(r'(?m)^source: (elm://section/section_[0-9a-f-]+)$', packet)
    payload = json.loads(packet.split(MARKER, 1)[1])
    locators = [payload['prefixes'].get('source', '') + source['source']
                for source in payload['sources']]
    assert len(locators) == len(set(locators))
    assert all(SOURCE.fullmatch(value) for value in locators)
    assert payload['coverage']['exact'] + payload['coverage']['manifest'] == len(locators)
    return locators
