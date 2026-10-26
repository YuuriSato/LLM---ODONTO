"""Copy only explicitly reviewed samples into a self-contained neural dataset."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.neural.dataset import DENTAL_CLASSES, SPLITS, digest, read_manifest


def build(review: Path, source: Path, output: Path):
    source = source.resolve()
    with review.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    selected = [row for row in rows if row.get('include', '').strip().lower() in {'yes', 'sim'}]
    if not selected:
        raise ValueError('Nenhuma amostra aprovada em include=yes; revise procedencia primeiro.')
    samples, groups, seen = [], {}, set()
    for row in selected:
        if row['verified_label'] not in DENTAL_CLASSES or row['split'] not in SPLITS:
            raise ValueError('Classe verificada ou particao invalida.')
        if any(not row.get(key, '').strip() for key in ('verified_group', 'provenance', 'reviewer', 'reviewed_at')):
            raise ValueError('Revisao incompleta: grupo, procedencia, revisor e data obrigatorios.')
        path = (source / row['file']).resolve()
        if not path.is_relative_to(source) or not path.is_file() or digest(path) != row['sha256']:
            raise ValueError('Imagem ausente, externa ou modificada desde o inventario.')
        if row['sha256'] in seen:
            raise ValueError('Selecione apenas uma copia de cada imagem duplicada.')
        seen.add(row['sha256'])
        group = row['verified_group']
        if group in groups and groups[group] != row['split']:
            raise ValueError('Grupo cruza particoes; mantenha paciente/original e variantes juntos.')
        groups[group] = row['split']
        samples.append({'id': row['sha256'], 'file': 'images/' + row['sha256'] + path.suffix.lower(),
                        'sha256': row['sha256'], 'label': row['verified_label'], 'split': row['split'],
                        'group': group, 'verified': True,
                        'provenance': row['provenance'] + ' | reviewed_by=' + row['reviewer'] + ' | reviewed_at=' + row['reviewed_at']})
    if any(not any(row['label'] == label and row['split'] == split for row in samples)
           for label in DENTAL_CLASSES for split in SPLITS):
        raise ValueError('Cada classe precisa de exemplos revisados nas tres particoes.')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'images').mkdir()
    for row, sample in zip(selected, samples):
        shutil.copy2(source / row['file'], output / sample['file'])
    manifest = {'schema_version': '1.0', 'scope': 'dental', 'classes': DENTAL_CLASSES, 'samples': samples}
    manifest_path = output / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    read_manifest(manifest_path)
    return manifest_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.review, args.source, args.output))
