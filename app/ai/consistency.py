"""Cross-check quality claims against their measured source, in every conclusion.

Narrative detection is a conservative supplementary guard for common Portuguese
claims, not a general natural-language truth verifier. Structured issues are
checked independently. Global quality does not establish regional visibility.
"""
import re
import unicodedata

from app.ai.schemas import IntegrityAnalysis, LocalEvidence
from app.local_forensics import QUALITY_MIN_SIDE, QUALITY_MIN_MEGAPIXELS, QUALITY_MIN_LAPLACIAN


def normalized(text: str) -> str:
    return ''.join(char for char in unicodedata.normalize('NFKD', text.lower())
                   if not unicodedata.combining(char))


def unsupported_authenticity_claims(texts: list[str]) -> list[dict[str, str]]:
    """Catch explicit unsupported origin inferences, not all paraphrases."""
    for text in texts:
        for sentence in re.split(r'[.!?;\n]', normalized(text)):
            absence = re.search(r'\b(?:ausencia de|sem) anomalias\b|\b(?:ausencia de|sem) (?:informacoes )?(?:exif|metadados)\b', sentence)
            if not absence:
                continue
            tail = sentence[absence.end():]
            inference = re.search(r'\b(?:sugerem|sugere|indicam|indica|comprovam|comprova|confirmam|confirma|demonstram|demonstra|garantem|garante)\b', tail)
            if not inference or re.search(r'\b(?:nao|nunca)\b', tail[:inference.start()]):
                continue
            outcome = tail[inference.end():]
            if re.search(r'\b(?:original|autentica|autenticidade)\b|nao foi gerada por ia|(?:processo|edicao) tradicional|(?:gerada|editada) por ia', outcome):
                return [{'code': 'unsupported_authenticity_inference',
                         'message': 'Ausencia de anomalias ou de EXIF nao estabelece autenticidade nem distingue edicao tradicional de IA. Descreva o que foi observado sem inferir a origem a partir dessa ausencia.'}]
    return []


def modality_text_conflicts(modality: str, texts: list[str]) -> list[dict[str, str]]:
    if modality == 'OUTRA':
        return []
    pattern = (r'\b(?:radiografia|radiografica|raios[- ]?x|x[- ]?ray)\b' if modality == 'INTRAORAL'
               else r'\b(?:fotografia|fotografica|photograph|photo)\b')
    for text in texts:
        for clause in re.split(r'[.!?;\n]|\bmas\b|\bporem\b', normalized(text)):
            for match in re.finditer(pattern, clause):
                prefix = clause[max(0, match.start() - 45):match.start()]
                if re.search(r'\b(?:nao|sem|not|no|ausencia|nenhum|nenhuma)\b', prefix):
                    continue
                return [{'code': 'modality_text_disagreement',
                         'message': 'A modalidade estruturada e a descricao textual divergem entre fotografia e imagem radiologica. Confira o arquivo e corrija ambos.'}]
    return []


def asserted_quality_problems(analysis: IntegrityAnalysis) -> set[str]:
    texts = [analysis.justificativa, *analysis.limitacoes]
    for values in analysis.analise_visual.model_dump().values():
        texts.extend(values)
    texts.extend(claim.descricao for claim in analysis.evidencias_favoraveis + analysis.evidencias_contrarias)
    patterns = {
        'resolucao_insuficiente': r'baixa resolucao|resolucao (?:muito )?(?:baixa|insuficiente)',
        'desfoque_extremo': r'desfoque (?:extremo|severo)|nitidez (?:global )?muito baixa',
    }
    found = set()
    for text in texts:
        for clause in re.split(r'[.!?;\n]|\bmas\b|\bporem\b', normalized(text)):
            for kind, pattern in patterns.items():
                for match in re.finditer(pattern, clause):
                    prefix = clause[max(0, match.start() - 45):match.start()]
                    if re.search(r'\b(?:nao|sem|ausencia de|nenhum|nenhuma)\b', prefix):
                        continue
                    found.add(kind)
    return found


def measured_quality_support(evidence: LocalEvidence) -> dict[str, bool | None]:
    records = {record.id: record for record in evidence.records}
    dimensions = records.get('dimensoes')
    sharpness = records.get('nitidez')
    supported: dict[str, bool | None] = {
        'resolucao_insuficiente': None,
        'desfoque_extremo': None,
    }
    if dimensions and dimensions.status == 'disponivel':
        side = dimensions.values.get('image_min_side')
        megapixels = dimensions.values.get('image_megapixels')
        if isinstance(side, (int, float)) and isinstance(megapixels, (int, float)):
            supported['resolucao_insuficiente'] = side < QUALITY_MIN_SIDE or megapixels < QUALITY_MIN_MEGAPIXELS
    if sharpness and sharpness.status == 'disponivel':
        laplacian = sharpness.values.get('laplacian_var')
        if isinstance(laplacian, (int, float)):
            supported['desfoque_extremo'] = laplacian < QUALITY_MIN_LAPLACIAN
    return supported


def quality_conflicts(analysis: IntegrityAnalysis, evidence: LocalEvidence) -> list[dict[str, str]]:
    supported = measured_quality_support(evidence)
    issues = {issue.tipo.value for issue in analysis.problemas_qualidade if issue.fonte == 'computacional'}
    narratives = asserted_quality_problems(analysis)
    result = []
    for kind in sorted(issues | narratives):
        # Unknown measurements cannot justify rejecting a visual observation.
        if supported.get(kind) is not False:
            continue
        label = 'baixa resolucao' if kind == 'resolucao_insuficiente' else 'desfoque extremo'
        result.append({
            'code': f'unsupported_{kind}',
            'message': f'Alegacao de {label} diverge das medicoes locais. Descreva uma limitacao regional concreta ou remova a alegacao global.',
        })
    return result
