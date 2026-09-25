"""Register a labeled sample without exposing labels in image filenames or prompts."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation import digest, load_manifest
from app.file_lock import file_lock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--group', required=True)
    parser.add_argument('--split', choices=['test', 'calibration'], required=True)
    parser.add_argument('--label', choices=['REAL', 'IA_GERADA', 'IA_EDITADA', 'EDICAO_TRADICIONAL', 'INDETERMINADO'])
    parser.add_argument('--provenance', required=True)
    parser.add_argument('--transformation')
    parser.add_argument('--verified', action='store_true', help='Atesta procedencia do rotulo; nao infira autenticidade da aparencia.')
    parser.add_argument('--scope', choices=['engineering', 'dental'], default='dental')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'datasets'
    print(register_sample(args, root))


def register_sample(args, root: Path):
    with file_lock(root.parent / '.dataset.lock'):
        return _register_sample(args, root)


def _register_sample(args, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'manifest.json'
    manifest = load_manifest(manifest_path).model_dump(mode='json') if manifest_path.exists() else {'schema_version': '1.0', 'samples': []}
    identifier = uuid.uuid4().hex
    image_path = root / (identifier + args.image.suffix.lower())
    copied = []
    staging = root / (identifier + '.json')
    try:
        shutil.copyfile(args.image, image_path)
        copied.append(image_path)
        reference = None
        if args.reference:
            reference_path = root / (uuid.uuid4().hex + args.reference.suffix.lower())
            shutil.copyfile(args.reference, reference_path)
            copied.append(reference_path)
            reference = reference_path.name
        manifest['samples'].append({'id': identifier, 'file': image_path.name, 'sha256': digest(image_path),
                                   'group': args.group, 'split': args.split, 'ground_truth': args.label,
                                   'provenance': args.provenance, 'verified': args.verified, 'scope': args.scope,
                                   'reference': reference, 'reference_sha256': digest(reference_path) if reference else None,
                                   'transformation': args.transformation})
        staging.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        load_manifest(staging)
        calibration = root.parent / 'integrity_calibration.json'
        if args.split == 'test' and calibration.exists():
            labels = json.loads(calibration.read_text(encoding='utf-8-sig'))
            if any(digest(path) in labels for path in copied):
                raise ValueError('Imagem ja esta na calibracao; nao pode entrar no teste.')
        staging.replace(manifest_path)
    except Exception:
        for path in copied:
            path.unlink(missing_ok=True)
        raise
    finally:
        staging.unlink(missing_ok=True)
    return identifier


if __name__ == '__main__':
    main()
