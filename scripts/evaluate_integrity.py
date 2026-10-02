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


def select_samples(manifest, *, sample_ids=(), verified_only=False, limit=None):
    if limit is not None and limit < 1:
        raise ValueError('O limite deve ser positivo.')
    wanted = set(sample_ids)
    samples = [sample for sample in manifest.samples if sample.split == 'test']
    if wanted - {sample.id for sample in samples}:
        raise ValueError('ID inexistente ou fora da particao de teste.')
    if wanted:
        samples = [sample for sample in samples if sample.id in wanted]
    if verified_only:
        samples = [sample for sample in samples if sample.verified and sample.ground_truth is not None]
    return samples[:limit] if limit is not None else samples


def evaluate_samples(samples, manifest_path, settings, root, *, continue_on_error=False):
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    selection = {'schema_version': '1.0', 'provider': settings.provider, 'model': settings.model,
                 'timeout_seconds': settings.timeout_seconds, 'max_output_tokens': settings.max_output_tokens,
                 'calibration_used': False, 'continue_on_error': continue_on_error,
                 'samples': [sample.model_dump(mode='json') for sample in samples]}
    (root / 'selection.json').write_text(json.dumps(selection, indent=2), encoding='utf-8')
    for sample in samples:
        image = dataset_file(manifest_path.parent, sample.file)
        reference = dataset_file(manifest_path.parent, sample.reference) if sample.reference else None
        result = run_integrity_pipeline(image, reference, settings=settings, cache_dir=root / 'analyses', calibration={})
        rows.append({'sample': sample.id, 'model': settings.provider + ':' + settings.model,
                     'quality': result['forensic_quality'], 'status': result['status'],
                     'predicted': result['verdict'], 'expected': sample.ground_truth.value if sample.ground_truth else None,
                     'verified': sample.verified, 'scope': sample.scope, 'analysis_id': result['analysis_id'],
                     'error_code': result.get('error_code'), 'duration_seconds': result.get('duration_seconds')})
        (root / 'rows.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        report = {scope: summarize([row for row in rows if row['scope'] == scope]) for scope in ('engineering', 'dental')}
        report['execution'] = {'planned': len(samples), 'attempted': len(rows),
                               'remaining': len(samples) - len(rows),
                               'stopped_on_error': result['status'] != 'concluida' and not continue_on_error}
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'{len(rows)}/{len(samples)}: {sample.id} {result["status"]}', flush=True)
        if result['status'] != 'concluida' and not continue_on_error:
            break
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--provider', choices=['gemini', 'lmstudio'], required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--sample', action='append', default=[], help='ID de teste; pode repetir a opcao.')
    parser.add_argument('--verified-only', action='store_true', help='Selecionar somente rotulos verificados.')
    parser.add_argument('--limit', type=int, help='Maximo de amostras, na ordem do manifesto.')
    parser.add_argument('--timeout-seconds', type=int, help='Timeout por chamada somente nesta rodada.')
    parser.add_argument('--continue-on-error', action='store_true', help='Continuar mesmo apos falha tecnica; padrao interrompe.')
    parser.add_argument('--run', action='store_true', help='Executar chamadas reais; sem esta opcao apenas valida o dataset.')
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    try:
        samples = select_samples(manifest, sample_ids=args.sample, verified_only=args.verified_only, limit=args.limit)
    except ValueError as exc:
        parser.error(str(exc))
    if args.timeout_seconds is not None and args.timeout_seconds < 1:
        parser.error('Timeout deve ser positivo.')
    if not args.run:
        print(json.dumps({'test_samples': len(samples), 'verified_labels': sum(s.verified and s.ground_truth is not None for s in samples)}))
        return 0
    if not samples:
        parser.error('Nenhuma amostra selecionada; nenhuma chamada sera executada.')
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'evaluations' / uuid.uuid4().hex
    settings = replace(get_settings(), provider=args.provider, model=args.model)
    if args.timeout_seconds is not None:
        settings = replace(settings, timeout_seconds=args.timeout_seconds)
    rows = evaluate_samples(samples, args.manifest, settings, root, continue_on_error=args.continue_on_error)
    print(root)
    return 0 if all(row['status'] == 'concluida' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
