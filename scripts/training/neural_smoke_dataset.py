"""Generate reproducible geometric controls to exercise training, never dental ground truth."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image
from app.neural.dataset import digest


def create_dataset(folder: Path, seed=17):
    folder.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(seed)
    classes = ['HORIZONTAL', 'VERTICAL', 'DIAGONAL', 'CIRCULAR']
    samples = []
    y, x = np.mgrid[:96, :96]
    for split, count in [('train', 16), ('validation', 6), ('test', 6)]:
        for label in classes:
            for index in range(count):
                phase, width = rng.uniform(0, 10), rng.uniform(7, 13)
                coordinate = {'HORIZONTAL': y, 'VERTICAL': x, 'DIAGONAL': x+y,
                              'CIRCULAR': np.sqrt((x-48)**2+(y-48)**2)}[label]
                texture = 127 + 75 * np.sin((coordinate+phase)/width*np.pi)
                pixels = np.stack([texture]*3, axis=-1) + rng.normal(0, 5, (96, 96, 3))
                identifier = f'{split}-{label}-{index}'
                path = folder / (identifier+'.png')
                Image.fromarray(np.clip(pixels, 0, 255).astype('uint8')).save(path)
                samples.append({'id': identifier, 'file': path.name, 'sha256': digest(path),
                                'group': identifier, 'split': split, 'label': label, 'verified': True,
                                'provenance': 'Geometric formula from neural_smoke_dataset.py; no dental or authenticity meaning.'})
    manifest = {'schema_version': '1.0', 'scope': 'engineering', 'classes': classes, 'samples': samples}
    path = folder / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(create_dataset(parser.parse_args().output))
