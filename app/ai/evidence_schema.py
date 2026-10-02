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
        section['properties']['interpretacao'] = {
            'type': 'string', 'const': 'Consulte as referencias verificadas.'
        }
        references = section['properties']['referencias']
        choices = reference_choices(record)
        if record.status == 'disponivel':
            if not choices:
                raise ValueError(f'Evidencia {name} sem medida escalar referenciavel.')
            references.update(items={'anyOf': choices}, minItems=1, maxItems=1)
        else:
            references.update(maxItems=0)
        definitions['ForensicAnalysis']['properties'][name] = section

    # Visual observations cannot masquerade as measured evidence, and vice versa.
    visual = deepcopy(definitions['Claim'])
    visual['properties']['descricao']['maxLength'] = 180
    visual['properties']['fonte'] = {'type': 'string', 'const': 'visual'}
    visual['properties']['referencias']['maxItems'] = 0
    computational = deepcopy(definitions['Claim'])
    computational['properties']['descricao']['maxLength'] = 180
    computational['properties']['fonte'] = {'type': 'string', 'const': 'computacional'}
    choices = [choice for record in evidence.records for choice in reference_choices(record)]
    computational['properties']['referencias'].update(items={'anyOf': choices}, minItems=1, maxItems=2)
    definitions['Claim'] = {'anyOf': [visual, computational]} if choices else visual

    for field in definitions['VisualAnalysis']['properties'].values():
        field['maxItems'] = 2
        field['items']['maxLength'] = 120
    quality_variants = []
    for issue_type, evidence_id in (
        ('desfoque_extremo', 'nitidez'),
        ('resolucao_insuficiente', 'dimensoes'),
    ):
        issue_references = reference_choices(records[evidence_id])
        if not issue_references:
            continue
        variant = deepcopy(definitions['QualityIssue'])
        variant['properties']['tipo'] = {'type': 'string', 'const': issue_type}
        variant['properties']['fonte'] = {'type': 'string', 'const': 'computacional'}
        variant['properties']['descricao']['maxLength'] = 180
        variant['properties']['referencias'].update(
            items={'anyOf': issue_references}, minItems=1, maxItems=2
        )
        quality_variants.append(variant)
    for issue_type in ('exposicao_inadequada', 'regiao_interesse_encoberta'):
        variant = deepcopy(definitions['QualityIssue'])
        variant['properties']['tipo'] = {'type': 'string', 'const': issue_type}
        variant['properties']['fonte'] = {'type': 'string', 'const': 'visual'}
        variant['properties']['descricao']['maxLength'] = 180
        variant['properties']['referencias']['maxItems'] = 0
        quality_variants.append(variant)
    definitions['QualityIssue'] = {'anyOf': quality_variants}
    schema['properties']['evidencias_favoraveis']['maxItems'] = 3
    schema['properties']['evidencias_contrarias']['maxItems'] = 3
    schema['properties']['problemas_qualidade']['maxItems'] = 2
    schema['properties']['limitacoes']['maxItems'] = 3
    schema['properties']['limitacoes']['items']['maxLength'] = 180
    schema['properties']['justificativa']['maxLength'] = 320

    variants = []
    for conclusion, verdicts, quality_min, quality_max in (
        ('classificada', ['REAL', 'IA_GERADA', 'IA_EDITADA', 'EDICAO_TRADICIONAL'], None, 0),
        ('inconclusiva', ['INDETERMINADO'], None, 0),
        ('impossivel_avaliar', ['INDETERMINADO'], 1, 2),
    ):
        variant = deepcopy(schema)
        variant.pop('$defs', None)
        variant['properties']['conclusion_type'] = {'type': 'string', 'const': conclusion}
        variant['properties']['veredito'] = {'type': 'string', 'enum': verdicts}
        variant['properties']['problemas_qualidade']['maxItems'] = quality_max
        if quality_min is not None:
            variant['properties']['problemas_qualidade']['minItems'] = quality_min
        variants.append(variant)
    return {'$defs': definitions, 'anyOf': variants}
