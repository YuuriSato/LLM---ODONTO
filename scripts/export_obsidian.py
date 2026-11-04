"""Export aggregate project knowledge to an Obsidian-compatible vault.

Does not export uploads, credentials, filenames, raw responses or patient data.
Existing generated files edited by the user are preserved and reported.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def snapshot(root: Path) -> dict:
    statuses, models, errors, conclusions = Counter(), Counter(), Counter(), Counter()
    unreadable = 0
    for path in (root / 'runtime/analysis_cache').glob('*/result.json'):
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            unreadable += 1
            continue
        statuses[str(result.get('status', 'desconhecido'))] += 1
        models[str(result.get('model', 'desconhecido'))] += 1
        conclusions[str(result.get('conclusion_type') or 'sem_conclusao')] += 1
        if result.get('error_code'):
            errors[str(result['error_code'])] += 1
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = 'indisponivel'
    return {'revision': revision, 'statuses': dict(statuses), 'models': dict(models),
            'errors': dict(errors), 'conclusions': dict(conclusions), 'unreadable': unreadable}


def export(vault: Path, root: Path = ROOT) -> dict:
    generated = vault / 'Gerado'
    generated.mkdir(parents=True, exist_ok=True)
    tracking = generated / '.export-manifest.json'
    previous = json.loads(tracking.read_text(encoding='utf-8')) if tracking.exists() else {}
    data = snapshot(root)
    text = ('---\ntags: [lm-odonto, gerado]\n---\n\n# Estado do projeto\n\n'
            'Gerado pelo comando `python scripts/export_obsidian.py`. Notas editadas manualmente são preservadas na próxima exportação.\n\n'
            f'Atualização UTC: {datetime.now(timezone.utc).isoformat()}\n\n'
            f'Commit: `{data["revision"]}`. Alterações locais podem existir além desse commit.\n\n'
            '[[Inicio]] · [[Arquitetura]] · [[Validacao]] · [[Rede neural]]\n\n'
            '## Execuções locais salvas\n\n```json\n' + json.dumps(data, ensure_ascii=False, indent=2) + '\n```\n\n'
            'Contagens incluem histórico anterior às correções; não medem acurácia nem procedência. Nenhum arquivo de imagem ou resposta individual é copiado.\n')
    files = {'Estado do projeto.md': text}
    saved, conflicts = [], []
    for name, content in files.items():
        path = generated / name
        if path.exists() and sha(path.read_text(encoding='utf-8')) != previous.get(name):
            conflicts.append(name)
            continue
        path.write_text(content, encoding='utf-8')
        previous[name] = sha(content)
        saved.append(name)
    tracking.write_text(json.dumps(previous, indent=2), encoding='utf-8')
    return {'saved': saved, 'preserved_user_edits': conflicts, 'vault': str(vault.resolve())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, default=ROOT / 'obsidian')
    result = export(parser.parse_args().vault)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result['preserved_user_edits'] else 0)
