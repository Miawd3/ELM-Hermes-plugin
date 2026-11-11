"""Closed, document-level typed-memory declarations (not inferred from prose)."""
from __future__ import annotations

import re

LANES = ('user', 'work', 'reference')
KINDS = ('explicit_fact', 'preference', 'observation', 'hypothesis',
         'interpretation', 'summary', 'procedure', 'reference')
LEGACY_KINDS = ('explicit_fact', 'preference', 'observation', 'hypothesis')
SENSITIVITIES = ('normal', 'sensitive_health')
BASES = ('explicit_statement', 'direct_observation', 'inference', 'source_document')
FIELDS = ('memory_lane', 'memory_kind', 'memory_sensitivity', 'memory_source', 'memory_basis')
SOURCE_PATTERN = r'elm://section/section_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'


def validate_metadata(meta: dict, project: str | None) -> None:
    if not any(key in meta for key in FIELDS):
        return  # Legacy unclassified: no semantic claim about arbitrary prose.
    if not all(key in meta for key in FIELDS):
        raise ValueError('Typed memory requires Memory lane, kind, basis, sensitivity and source.')
    if (meta['memory_lane'] not in LANES or meta['memory_kind'] not in KINDS
            or meta['memory_sensitivity'] not in SENSITIVITIES
            or meta['memory_basis'] not in BASES
            or re.fullmatch(SOURCE_PATTERN, meta['memory_source']) is None):
        raise ValueError('Invalid closed typed-memory metadata.')
    if not project or meta.get('record_type') == 'claim':
        raise ValueError('Typed declarations require a project document, not a governed claim.')
    if meta['memory_lane'] == 'user' and meta['memory_kind'] not in LEGACY_KINDS:
        raise ValueError('New review kinds are work/reference only; user communication policy is unchanged.')
    allowed_bases = {'explicit_fact': {'explicit_statement', 'source_document'},
                     'preference': {'explicit_statement'},
                     'observation': {'direct_observation', 'source_document'},
                     'hypothesis': {'inference'}, 'interpretation': {'inference'},
                     'summary': {'source_document', 'inference'},
                     'procedure': {'source_document', 'inference'},
                     'reference': {'source_document'}}
    if (meta['memory_basis'] not in allowed_bases[meta['memory_kind']]
            or (meta['memory_lane'] == 'user' and meta['memory_kind'] == 'explicit_fact'
                and meta['memory_basis'] != 'explicit_statement')):
        raise ValueError('Kind/basis mismatch: inference is a hypothesis, never an explicit fact/preference.')


def intent(args) -> tuple[str, str]:
    lane = getattr(args, 'memory_lane', None)
    purpose = getattr(args, 'memory_purpose', None)
    if lane is None and purpose is None:
        return 'work', 'task'
    if (lane not in LANES or purpose not in ('task', 'communication', 'review')
            or (lane == 'user') != (purpose == 'communication')):
        raise ValueError('Select user/communication, work/task, reference/task or explicit work/reference review together.')
    if purpose == 'review' and not getattr(args, 'project', None):
        raise ValueError('Review requires an explicit project grant.')
    if lane != 'work' and not getattr(args, 'project', None):
        raise ValueError('Non-work memory intent requires an explicit project grant.')
    return lane, purpose


def metadata(con, document_id: int) -> dict | None:
    meta = dict(con.execute("SELECT key,value FROM properties WHERE document_id=? AND key LIKE 'memory_%'", (document_id,)))
    if not meta:
        return None
    restriction = (('communication_only_uncertain' if meta['memory_lane'] == 'user'
                    else 'untrusted_evidence_only_uncertain') if meta['memory_basis'] == 'inference' else
                   'communication_only' if meta['memory_lane'] == 'user' else 'untrusted_evidence_only')
    return {'schema_version': 1, **{k.removeprefix('memory_'): meta[k] for k in FIELDS},
            'restriction': restriction}


def annotate(con, row: dict) -> dict:
    memory = metadata(con, int(row.get('document_id', row.get('id'))))
    if memory:
        row['memory'] = memory
        authority = {'explicit_fact': 'declared_statement_not_verified',
                     'preference': 'declared_preference_not_verified',
                     'observation': 'unverified_observation',
                     'hypothesis': 'unverified_hypothesis',
                     'interpretation': 'unverified_interpretation',
                     'summary': 'unverified_summary',
                     'procedure': 'untrusted_procedure_draft',
                     'reference': 'untrusted_reference'}[memory['kind']]
        row['authority'] = authority
        if (memory['sensitivity'] == 'sensitive_health' and memory['kind'] == 'explicit_fact'
                and memory['basis'] == 'explicit_statement'):
            row['authority'] = 'declared_self_report_not_medically_verified'
    return row


def policy_sql(alias: str, args, *, policy_moment: str) -> tuple[list[str], list[object]]:
    # One predicate shared by search, supplemental selection and direct reads.
    # Typed user/reference records can never enter the legacy/default work lane.
    lane, purpose = intent(args)
    typed = f"SELECT 1 FROM properties memory_policy WHERE memory_policy.document_id={alias}.id AND memory_policy.key='memory_lane'"
    restrictions = []
    params = []
    # A declaration is not evidence: require its concrete source to resolve in
    # this same project, without retrieving or widening access to source text.
    source_policy = ''
    if not getattr(args, 'include_archive', False):
        source_policy += ' AND md.is_archive=0'
    if not getattr(args, 'include_history', False):
        source_policy += " AND NOT EXISTS (SELECT 1 FROM claims mc WHERE mc.document_id=md.id AND (mc.status<>'accepted' OR mc.valid_from>? OR (mc.valid_to IS NOT NULL AND mc.valid_to<=?)))"
        params.extend((policy_moment, policy_moment))
    restrictions.append(f"(NOT EXISTS ({typed}) OR EXISTS (SELECT 1 FROM properties mp JOIN sections ms ON ('elm://section/' || ms.section_key)=mp.value JOIN documents md ON md.id=ms.document_id WHERE mp.document_id={alias}.id AND mp.key='memory_source' AND md.project={alias}.project {source_policy}))")
    sensitive = f"EXISTS (SELECT 1 FROM properties mp WHERE mp.document_id={alias}.id AND mp.key='memory_sensitivity' AND mp.value='sensitive_health')"
    # No diagnosis classifier: declared health inferences/observations are
    # retained as source, but withheld from every model-facing selection.
    if lane == 'user' and purpose == 'communication':
        self_report = f"EXISTS (SELECT 1 FROM properties mp WHERE mp.document_id={alias}.id AND mp.key='memory_kind' AND mp.value='explicit_fact') AND EXISTS (SELECT 1 FROM properties mp WHERE mp.document_id={alias}.id AND mp.key='memory_basis' AND mp.value='explicit_statement')"
        restrictions.append(f"(NOT {sensitive} OR ({self_report}))")
    else:
        restrictions.append(f"NOT {sensitive}")
    if purpose not in ('communication', 'review'):
        restrictions.append(f"NOT EXISTS (SELECT 1 FROM properties mp WHERE mp.document_id={alias}.id AND mp.key='memory_basis' AND mp.value='inference')")
    if lane == 'work':
        return [*restrictions, f"NOT EXISTS ({typed} AND memory_policy.value<>'work')"], params
    return [*restrictions, f"EXISTS ({typed} AND memory_policy.value=?)"], [*params, lane]
