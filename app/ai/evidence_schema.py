"""Constrain local grammar sampling to measurements actually collected for this image."""
from copy import deepcopy

from app.ai.schemas import ForensicAnalysis, IntegrityAnalysis, LocalEvidence


SCHEMA_MODE = 'evidence-bound-1'


def reference_choices(record):
    if record.status != 'disponivel':
        return []
    types = {str: 'string', int: 'integer', float: 'number', bool: 'boolean', type(None): 'null'}
    return [
        {'type': 'object', 'additionalProperties': False,
         'properties': {'evidence_id': {'type': 'string', 'const': record.id},
                        'metric': {'type': 'string', 'const': metric},
                        'value': {'type': types[type(value)], 'const': value}},
         'required': ['evidence_id', 'metric', 'value']}
        for metric, value in record.values.items() if type(value) in types
    ]


def bound_integrity_schema(evidence: LocalEvidence) -> dict:
    schema = IntegrityAnalysis.model_json_schema()
    definitions = schema['$defs']
    records = {record.id: record for record in evidence.records}
    for name in ForensicAnalysis.model_fields:
        record = records[name]
        section = deepcopy(definitions['Interpretation'])
        section['properties']['status'] = {'type': 'string', 'const': record.status}
        references = section['properties']['referencias']
        choices = reference_choices(record)
        if record.status == 'disponivel':
            if not choices:
                raise ValueError(f'Evidencia {name} sem medida escalar referenciavel.')
            references.update(items={'anyOf': choices}, minItems=1)
        else:
            references.update(maxItems=0)
        definitions['ForensicAnalysis']['properties'][name] = section

    # Visual observations cannot masquerade as measured evidence, and vice versa.
    visual = deepcopy(definitions['Claim'])
    visual['properties']['fonte'] = {'type': 'string', 'const': 'visual'}
    visual['properties']['referencias']['maxItems'] = 0
    computational = deepcopy(definitions['Claim'])
    computational['properties']['fonte'] = {'type': 'string', 'const': 'computacional'}
    choices = [choice for record in evidence.records for choice in reference_choices(record)]
    computational['properties']['referencias'].update(items={'anyOf': choices}, minItems=1)
    definitions['Claim'] = {'anyOf': [visual, computational]} if choices else visual
    return schema
