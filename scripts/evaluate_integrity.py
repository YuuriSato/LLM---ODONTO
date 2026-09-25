"""Explicit paid/local evaluation. Labels and provenance never enter provider prompts."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai.config import get_settings
from app.ai.pipeline import run_integrity_pipeline
from app.evaluation import load_manifest, dataset_file, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--provider', choices=['gemini', 'lmstudio'], required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--run', action='store_true', help='Executar chamadas reais; sem esta opcao apenas valida o dataset.')
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    samples = [sample for sample in manifest.samples if sample.split == 'test']
    if not args.run:
        print(json.dumps({'test_samples': len(samples), 'verified_labels': sum(s.verified and s.ground_truth is not None for s in samples)}))
        return
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'evaluations' / uuid.uuid4().hex
    root.mkdir(parents=True)
    settings = replace(get_settings(), provider=args.provider, model=args.model)
    rows = []
    for sample in samples:
        image = dataset_file(args.manifest.parent, sample.file)
        reference = dataset_file(args.manifest.parent, sample.reference) if sample.reference else None
        result = run_integrity_pipeline(image, reference, settings=settings, cache_dir=root / 'analyses', calibration={})
        rows.append({'sample': sample.id, 'model': args.provider + ':' + args.model,
                     'quality': result['forensic_quality'], 'status': result['status'],
                     'predicted': result['verdict'], 'expected': sample.ground_truth.value if sample.ground_truth else None,
                     'verified': sample.verified, 'scope': sample.scope, 'analysis_id': result['analysis_id']})
        (root / 'rows.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    report = {scope: summarize([row for row in rows if row['scope'] == scope]) for scope in ('engineering', 'dental')}
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(root)


if __name__ == '__main__':
    main()
