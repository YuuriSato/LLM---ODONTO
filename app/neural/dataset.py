"""Verified image manifest with disjoint source groups and content hashes."""
from collections import Counter
import hashlib
import json
from pathlib import Path

DENTAL_CLASSES = ['REAL', 'EDICAO_TRADICIONAL', 'IA_GERADA', 'IA_EDITADA']
SPLITS = {'train', 'validation', 'test'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != '1.0' or manifest.get('scope') not in {'engineering', 'dental'}:
        raise ValueError('Manifesto neural exige schema_version 1.0 e scope engineering/dental.')
    classes = manifest.get('classes')
    if not isinstance(classes, list) or len(classes) < 2 or any(not isinstance(c, str) or not c for c in classes) or len(set(classes)) != len(classes):
        raise ValueError('Classes ausentes ou duplicadas.')
    if manifest['scope'] == 'dental' and classes != DENTAL_CLASSES:
        raise ValueError('Dataset dental exige as quatro classes de integridade na ordem documentada.')
    rows = manifest.get('samples')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Dataset vazio.')
    groups, hashes, ids = {}, set(), set()
    counts = Counter()
    for row in rows:
        for key in ('id', 'group', 'file', 'sha256', 'provenance', 'label', 'split'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'Campo obrigatorio ausente: {key}.')
        if row.get('verified') is not True:
            raise ValueError('Rotulos sem procedencia verificada nao podem entrar no treino.')
        if row['id'] in ids or row['label'] not in classes or row['split'] not in SPLITS:
            raise ValueError('ID duplicado, classe ou particao invalida.')
        ids.add(row['id'])
        source = (path.parent / row['file']).resolve()
        if not source.is_relative_to(path.parent.resolve()) or not source.is_file():
            raise ValueError('Imagem fora da pasta do manifesto ou inexistente.')
        actual = digest(source)
        if actual != row['sha256']:
            raise ValueError('Hash de imagem divergente.')
        if actual in hashes:
            raise ValueError('Imagem duplicada, inclusive entre particoes.')
        hashes.add(actual)
        if row['group'] in groups and groups[row['group']] != row['split']:
            raise ValueError('Vazamento: original/paciente/grupo em particoes diferentes.')
        groups[row['group']] = row['split']
        counts[row['split'], row['label']] += 1
    if any(not counts[split, label] for split in SPLITS for label in classes):
        raise ValueError('Cada classe deve estar presente em treino, validacao e teste.')
    return manifest
