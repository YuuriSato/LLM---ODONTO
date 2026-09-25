"""Explicit live multimodal gate. Uses a synthetic pattern, never patient images."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from app.ai.config import get_settings
from app.ai.pipeline import run_integrity_pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['gemini', 'lmstudio'], required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'provider_checks'
    root.mkdir(parents=True, exist_ok=True)
    image_path = root / 'synthetic-pattern.png'
    if not image_path.exists():
        image = Image.new('RGB', (640, 480), '#cccccc')
        draw = ImageDraw.Draw(image)
        for x in range(0, 640, 32):
            draw.rectangle((x, 80, x + 12, 400), fill=(x % 256, 100, 180))
        image.save(image_path)
    settings = replace(get_settings(), provider=args.provider, model=args.model)
    result = run_integrity_pipeline(image_path, settings=settings, cache_dir=root / 'analyses')
    passed = result['status'] == 'concluida' and result['audit_status'] == 'executada'
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'provider': args.provider,
              'model': args.model, 'passed': passed, 'analysis_id': result['analysis_id'],
              'error_code': result.get('error_code'), 'error': result.get('error'),
              'scope': 'transport_schema_evidence_audit_only_not_accuracy'}
    filename = args.provider + '-' + ''.join(c if c.isalnum() or c in '-_' else '_' for c in args.model) + '.json'
    (root / filename).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
