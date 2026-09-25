"""Reproducible dataset contracts and classification metrics, separate from inference."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field
from app.ai.schemas import StrictModel, Verdict


class DatasetSample(StrictModel):
    id: str = Field(min_length=1)
    file: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    group: str = Field(min_length=1)
    split: Literal['calibration', 'test']
    ground_truth: Verdict | None
    provenance: str = Field(min_length=1)
    verified: bool
    scope: Literal['engineering', 'dental']
    reference: str | None = None
    reference_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    transformation: str | None = None


class DatasetManifest(StrictModel):
    schema_version: Literal['1.0']
    samples: list[DatasetSample]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataset_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Arquivo do dataset invalido ou fora da pasta.')
    return path


def load_manifest(path: Path) -> DatasetManifest:
    manifest = DatasetManifest.model_validate_json(path.read_text(encoding='utf-8'))
    ids, groups, hashes, image_hashes = set(), {}, {}, set()
    for sample in manifest.samples:
        if sample.id in ids:
            raise ValueError('ID duplicado no dataset.')
        ids.add(sample.id)
        if digest(dataset_file(path.parent, sample.file)) != sample.sha256:
            raise ValueError('Hash do dataset nao confere.')
        if sample.sha256 in image_hashes:
            raise ValueError('Imagem duplicada no dataset.')
        image_hashes.add(sample.sha256)
        for mapping, key in ((groups, sample.group), (hashes, sample.sha256)):
            if key in mapping and mapping[key] != sample.split:
                raise ValueError('Vazamento entre teste e calibracao.')
            mapping[key] = sample.split
        if sample.reference:
            reference_hash = digest(dataset_file(path.parent, sample.reference))
            if reference_hash != sample.reference_sha256:
                raise ValueError('Hash da referencia ausente ou divergente.')
            if reference_hash in hashes and hashes[reference_hash] != sample.split:
                raise ValueError('Referencia cruza teste e calibracao.')
            hashes[reference_hash] = sample.split
        elif sample.reference_sha256:
            raise ValueError('Hash de referencia sem arquivo.')
    return manifest


def held_out_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    manifest = load_manifest(path)
    result = set()
    for sample in manifest.samples:
        if sample.split == 'test':
            result.add(sample.sha256)
            if sample.reference:
                result.add(digest(dataset_file(path.parent, sample.reference)))
    return result


def summarize(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[(row['model'], row.get('quality', 'desconhecida'))].append(row)
    result = []
    for (model, quality), items in sorted(groups.items()):
        eligible = [item for item in items if item.get('verified') and item.get('expected') not in (None, 'INDETERMINADO')]
        completed = [item for item in eligible if item['status'] == 'concluida']
        decided = [item for item in completed if item.get('predicted') not in (None, 'INDETERMINADO')]
        confusion = Counter((item['expected'], item.get('predicted') if item['status'] == 'concluida' else 'NAO_CONCLUIDA') for item in eligible)
        actual_real = [item for item in completed if item['expected'] == 'REAL']
        actual_changed = [item for item in completed if item['expected'] != 'REAL']
        fp = sum(item.get('predicted') not in (None, 'REAL', 'INDETERMINADO') for item in actual_real)
        fn = sum(item.get('predicted') == 'REAL' for item in actual_changed)
        result.append({
            'model': model, 'quality': quality, 'total': len(items), 'eligible': len(eligible),
            'technical_failures': sum(item['status'] != 'concluida' for item in eligible),
            'indeterminate': sum(item.get('predicted') == 'INDETERMINADO' for item in completed),
            'coverage': len(decided) / len(eligible) if eligible else None,
            'accuracy_on_decided': sum(item['expected'] == item['predicted'] for item in decided) / len(decided) if decided else None,
            'false_positives': fp, 'false_negatives': fn,
            'false_positive_rate_completed_real': fp / len(actual_real) if actual_real else None,
            'false_negative_rate_completed_changed': fn / len(actual_changed) if actual_changed else None,
            'confusion': [{'expected': a, 'predicted': b, 'count': count} for (a, b), count in sorted(confusion.items())],
        })
    return {'schema_version': '1.0', 'groups': result,
            'confidence_is_calibrated': False,
            'limitations': ['Abstencoes nao sao acertos. Taxas excluem falhas tecnicas; cobertura e falhas sao reportadas separadamente.',
                            'Amostras sem procedencia verificada nao entram na acuracia. Resultados dependem da representatividade do dataset.']}
