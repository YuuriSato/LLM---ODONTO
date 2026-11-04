"""Create a deduplicated review queue without approving provenance or labels."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


def build_queue(review: Path, output: Path):
    with review.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('Inventario vazio.')
    hashes = defaultdict(list)
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    for row in rows:
        hashes[row['sha256']].append(row)
        # Merge filename candidate groups bridged by an identical file.
        union('hash:' + row['sha256'], 'name:' + row['group_candidate'])
    entries = []
    for sha, copies in sorted(hashes.items()):
        labels = sorted({row['candidate_label'] for row in copies} - {'SEM_ROTULO'})
        entries.append({
            'sha256': sha, 'files': sorted(row['file'] for row in copies),
            'candidate_labels': labels, 'label_conflict': len(labels) > 1,
            'review_group_candidate': find('hash:' + sha),
            'read_errors': sorted({row['read_error'] for row in copies if row['read_error']}),
            'verified': False,
        })
    summary = {
        'files': len(rows), 'unique_contents': len(entries),
        'duplicate_copies': len(rows) - len(entries),
        'conflicting_labels': sum(entry['label_conflict'] for entry in entries),
        'candidate_components': len({entry['review_group_candidate'] for entry in entries}),
        'unique_label_candidates': dict(Counter('|'.join(e['candidate_labels']) or 'SEM_ROTULO' for e in entries)),
        'warning': 'Groups combine exact hashes and filename hints. They do not establish patient identity, provenance or verified labels.',
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / 'queue.json').write_text(json.dumps({'summary': summary, 'entries': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    instructions = '''# Fila de revisão por conteúdo único

Cada entrada de `queue.json` corresponde a um SHA-256 e lista todas as cópias.
`candidate_labels` vem das pastas; não comprova autenticidade.
`review_group_candidate` une cópias idênticas e sugestões por nome. Revise o
paciente/original e variantes antes de usá-lo como grupo definitivo. Nomes iguais
podem unir imagens sem relação; nomes diferentes podem esconder o mesmo paciente.

Para cada entrada, confirme origem, transformação e rótulo com registros externos
à aparência da imagem. Se houver conflito ou procedência desconhecida, mantenha
fora do treino. Registre sua decisão em uma única cópia no `review.csv` original;
preencha `verified_label`, `verified_group`, `provenance`, `reviewer`, `reviewed_at`
e `split`, e só então marque `include=yes`. Deixe as demais cópias como `no`.
Todas as variantes do mesmo paciente/original devem usar a mesma partição.

Esta fila não altera imagens, decisões anteriores nem aprova rótulos.
'''
    (output / 'README.md').write_text(instructions, encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_queue(args.review, args.output), ensure_ascii=False, indent=2))
