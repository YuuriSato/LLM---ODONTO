from enum import Enum
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Verdict(str, Enum):
    REAL = "REAL"
    IA_GERADA = "IA_GERADA"
    IA_EDITADA = "IA_EDITADA"
    EDICAO_TRADICIONAL = "EDICAO_TRADICIONAL"
    INDETERMINADO = "INDETERMINADO"


class ConclusionType(str, Enum):
    CLASSIFICADA = "classificada"
    INCONCLUSIVA = "inconclusiva"
    IMPOSSIVEL_AVALIAR = "impossivel_avaliar"


class QualityIssueType(str, Enum):
    DESFOQUE_EXTREMO = "desfoque_extremo"
    RESOLUCAO_INSUFICIENTE = "resolucao_insuficiente"
    EXPOSICAO_INADEQUADA = "exposicao_inadequada"
    REGIAO_INTERESSE_ENCOBERTA = "regiao_interesse_encoberta"


EvidenceStatus = Literal["disponivel", "ausente", "nao_aplicavel", "falhou", "desativado"]


class EvidenceRecord(StrictModel):
    id: str
    family: str
    status: EvidenceStatus
    method: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    values: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    signal: Literal["anomalia", "sem_anomalia", "descritivo", "desconhecido"] = "descritivo"

    @field_validator("values", "parameters")
    @classmethod
    def finite_values(cls, value):
        def check(item):
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Metricas devem ser finitas.")
            if isinstance(item, dict):
                for child in item.values():
                    check(child)
            if isinstance(item, list):
                for child in item:
                    check(child)
        check(value)
        return value


class LocalEvidence(StrictModel):
    schema_version: str
    analysis_id: str
    image_sha256: str
    reference_sha256: str | None
    quality: Literal["boa", "limitada", "insuficiente", "desconhecida"]
    records: list[EvidenceRecord]
    observations: list[str]
    limitations: list[str]


class EvidenceReference(StrictModel):
    evidence_id: str
    metric: str
    value: str | float | bool | None


class Claim(StrictModel):
    descricao: str = Field(min_length=1)
    fonte: Literal["visual", "computacional"]
    referencias: list[EvidenceReference]


class QualityIssue(StrictModel):
    tipo: QualityIssueType
    descricao: str = Field(min_length=1)
    fonte: Literal["visual", "computacional"]
    referencias: list[EvidenceReference]


class Interpretation(StrictModel):
    status: EvidenceStatus
    interpretacao: str
    referencias: list[EvidenceReference]


class VisualAnalysis(StrictModel):
    anatomia_dental: list[str]
    texturas: list[str]
    bordas: list[str]
    iluminacao: list[str]
    artefatos_suspeitos: list[str]


class ForensicAnalysis(StrictModel):
    ela: Interpretation
    fft: Interpretation
    ruido: Interpretation
    ruido_blocos: Interpretation
    nitidez: Interpretation
    compressao: Interpretation
    metadata: Interpretation
    detector_ia: Interpretation
    comparacao: Interpretation


class IntegrityAnalysis(StrictModel):
    conclusion_type: ConclusionType
    veredito: Verdict
    confidence: float = Field(ge=0, le=1)
    modalidade: Literal["INTRAORAL", "RADIOGRAFIA", "PANORAMICA", "TOMOGRAFIA", "OUTRA"]
    justificativa: str = Field(min_length=1)
    analise_visual: VisualAnalysis
    analise_forense: ForensicAnalysis
    evidencias_favoraveis: list[Claim]
    evidencias_contrarias: list[Claim]
    problemas_qualidade: list[QualityIssue]
    limitacoes: list[str]
    requer_auditoria: bool


def validate_references(analysis: IntegrityAnalysis, evidence: LocalEvidence) -> None:
    records = {record.id: record for record in evidence.records}

    def check(ref: EvidenceReference):
        record = records.get(ref.evidence_id)
        if record is None or record.status != "disponivel" or ref.metric not in record.values:
            raise ValueError("Referencia forense inexistente ou indisponivel.")
        expected = record.values[ref.metric]
        # bool and int compare equal in Python; they are not equivalent measurements.
        if isinstance(expected, bool) != isinstance(ref.value, bool) or expected != ref.value:
            raise ValueError("Valor citado diverge da medicao local.")

    for section_name in ForensicAnalysis.model_fields:
        section = getattr(analysis.analise_forense, section_name)
        if re.search(r"\d", section.interpretacao):
            raise ValueError("Valores numericos forenses devem aparecer nas referencias, nao no texto livre.")
        record = records[section_name]
        if section.status != record.status:
            raise ValueError(f"Estado incorreto para {section_name}.")
        if section.status == "disponivel" and not section.referencias:
            raise ValueError(f"Interpretacao sem referencias: {section_name}.")
        if section.status != "disponivel" and section.referencias:
            raise ValueError(f"Referencia a metodo indisponivel: {section_name}.")
        for ref in section.referencias:
            if ref.evidence_id != section_name:
                raise ValueError("Referencia pertence a outra secao forense.")
            check(ref)
    for claim in analysis.evidencias_favoraveis + analysis.evidencias_contrarias:
        if claim.fonte == "computacional" and re.search(r"\d", claim.descricao):
            raise ValueError("Valores computacionais devem ser citados por referencias verificaveis.")
        if claim.fonte == "computacional" and not claim.referencias:
            raise ValueError("Alegacao computacional sem suporte.")
        if claim.fonte == "visual" and claim.referencias:
            raise ValueError("Observacao visual nao deve simular medicao computacional.")
        for ref in claim.referencias:
            check(ref)

    computational_quality = {
        QualityIssueType.DESFOQUE_EXTREMO: {"nitidez"},
        QualityIssueType.RESOLUCAO_INSUFICIENTE: {"dimensoes"},
    }
    visual_quality = {
        QualityIssueType.EXPOSICAO_INADEQUADA,
        QualityIssueType.REGIAO_INTERESSE_ENCOBERTA,
    }
    for issue in analysis.problemas_qualidade:
        if re.search(r"\d", issue.descricao):
            raise ValueError("Problemas de qualidade devem citar valores por referencias, nao no texto livre.")
        if issue.fonte == "computacional":
            allowed = computational_quality.get(issue.tipo)
            if not allowed or not issue.referencias:
                raise ValueError("Problema computacional de qualidade sem suporte permitido.")
            if any(ref.evidence_id not in allowed for ref in issue.referencias):
                raise ValueError("Problema de qualidade referencia uma metrica incompatível.")
        else:
            if issue.tipo not in visual_quality or issue.referencias:
                raise ValueError("Problema visual de qualidade nao deve simular medicao computacional.")
        for ref in issue.referencias:
            check(ref)

    if analysis.conclusion_type == ConclusionType.CLASSIFICADA and analysis.veredito == Verdict.INDETERMINADO:
        raise ValueError("Conclusao classificada exige um veredito definido.")
    if analysis.conclusion_type != ConclusionType.CLASSIFICADA and analysis.veredito != Verdict.INDETERMINADO:
        raise ValueError("Conclusao inconclusiva ou impossivel deve usar INDETERMINADO.")
    if analysis.conclusion_type == ConclusionType.IMPOSSIVEL_AVALIAR and not analysis.problemas_qualidade:
        raise ValueError("Impossivel de avaliar exige problemas bloqueantes de qualidade.")
    if analysis.conclusion_type != ConclusionType.IMPOSSIVEL_AVALIAR and analysis.problemas_qualidade:
        raise ValueError("Problemas bloqueantes so podem acompanhar Impossivel de avaliar.")
