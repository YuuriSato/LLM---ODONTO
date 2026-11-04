"""Replay the legacy transformation recipe in memory, preserving all source files."""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random
import sys

from PIL import Image, ImageFilter, __version__ as pillow_version

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.training.synthesize_training_variants import iter_images, draw_manual_marks, apply_digital_edit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(dataset, output, seed=7, limit=250):
    if output.exists():
        raise FileExistsError(output)
    images = iter_images(dataset / 'real')
    if not images:
        raise ValueError('Nenhuma imagem-base encontrada.')
    previous_state = random.getstate()
    records = []
    def compare(source, generated, target, quality, transformation):
        buffer = BytesIO()
        generated.save(buffer, format='JPEG', quality=quality)
        expected = digest(buffer.getvalue())
        observed = digest(target.read_bytes()) if target.is_file() else None
        records.append({'source': source.relative_to(dataset).as_posix(),
                        'source_sha256': digest(source.read_bytes()),
                        'target': target.relative_to(dataset).as_posix(),
                        'target_sha256': observed, 'reproduced_sha256': expected,
                        'transformation': transformation,
                        'status': 'exact_match' if observed == expected else ('missing' if observed is None else 'mismatch')})
    try:
        random.seed(seed)
        selected = random.sample(images, min(limit, len(images)))
        for index, source in enumerate(selected, 1):
            with Image.open(source) as image:
                manual = draw_manual_marks(image.copy())
                digital = apply_digital_edit(image.copy())
            stem = f'{index:04d}_{source.stem}'
            compare(source, manual, dataset / 'alterada_manualmente' / f'{stem}_manual.jpg', 92, 'drawn_marks')
            compare(source, digital, dataset / 'alterada_digitalmente' / f'{stem}_digital.jpg', 92, 'copy_paste')
        for index, source in enumerate(selected[:max(1, len(selected)//5)], 1):
            with Image.open(source) as image:
                degraded = image.convert('RGB').resize((max(64, image.width//4), max(64, image.height//4))).filter(ImageFilter.GaussianBlur(radius=2.0))
            compare(source, degraded, dataset / 'indeterminado' / f'{index:04d}_{source.stem}_low_quality.jpg', 35, 'degradation')
    finally:
        random.setstate(previous_state)
    result = {'seed': seed, 'limit': limit, 'pillow_version': pillow_version,
              'recipe_sha256': digest(Path(__file__).with_name('synthesize_training_variants.py').read_bytes()),
              'summary': dict(Counter(record['status'] for record in records)),
              'scope': 'Byte-exact reproducibility of transformations only; does not establish clinical provenance or source authenticity.',
              'records': records}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return result['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path('data/dataset_dental'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(audit(args.dataset, args.output))
