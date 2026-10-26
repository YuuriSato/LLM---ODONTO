"""Inventory existing images for human provenance review; never assign verified labels."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
LABELS = {'real': 'REAL', 'alterada_manualmente': 'EDICAO_TRADICIONAL',
          'alterada_digitalmente': 'EDICAO_TRADICIONAL', 'ia': 'IA_ORIGEM_A_REVISAR',
          'indeterminado': 'SEM_ROTULO'}


def source_stem(path):
    stem = path.stem
    if path.parent.name in {'alterada_manualmente', 'alterada_digitalmente', 'indeterminado'}:
        stem = re.sub(r'^\d{4}_', '', stem)
        stem = re.sub(r'_(manual|digital|low_quality)$', '', stem)
    return stem.casefold()


def inventory(source: Path, output: Path):
    source = source.resolve()
    if not source.is_dir():
        raise ValueError('Pasta de origem inexistente.')
    if output.resolve().is_relative_to(source):
        raise ValueError('Inventario deve ficar fora da pasta de origem.')
    output.mkdir(parents=True, exist_ok=False)
    rows, duplicates, groups = [], defaultdict(list), defaultdict(list)
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if not path.resolve().is_relative_to(source):
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(source).as_posix()
        row = {'file': relative, 'sha256': sha, 'candidate_label': LABELS.get(path.parent.name, 'SEM_ROTULO'),
               'group_candidate': hashlib.sha256(source_stem(path).encode()).hexdigest()[:20],
               'width': '', 'height': '', 'format': '', 'read_error': '',
               'verified_label': '', 'verified_group': '', 'provenance': '',
               'reviewer': '', 'reviewed_at': '', 'split': '', 'include': 'no'}
        try:
            with Image.open(path) as image:
                image.load()
                row.update(width=image.width, height=image.height, format=image.format)
        except (OSError, ValueError) as exc:
            row['read_error'] = type(exc).__name__
        duplicates[sha].append(relative)
        groups[row['group_candidate']].append(relative)
        rows.append(row)
    if not rows:
        raise ValueError('Nenhuma imagem encontrada.')
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {'source': str(source), 'files': len(rows), 'unique_sha256': len(duplicates),
               'duplicate_copies': len(rows)-len(duplicates),
               'candidate_labels': dict(Counter(row['candidate_label'] for row in rows)),
               'formats': dict(Counter(row['format'] for row in rows)),
               'unreadable': sum(bool(row['read_error']) for row in rows),
               'candidate_groups': len(groups), 'verified_labels': 0,
               'group_method': 'Filename matching only; human review required for original/patient and augmented variants.'}
    (output / 'inventory.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'duplicates.json').write_text(json.dumps({k:v for k,v in duplicates.items() if len(v)>1}, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'groups.json').write_text(json.dumps({k:v for k,v in groups.items() if len(v)>1}, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inventory(args.source, args.output), ensure_ascii=False, indent=2))
