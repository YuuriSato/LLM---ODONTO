from __future__ import annotations

import email.policy
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from email.parser import BytesParser
from io import BytesIO
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

import ollama

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ai.config import SUPPORTED_MODELS, get_settings
from app.ai.gemini_client import GeminiClient
from app.ai import lmstudio_client
from app.history_store import HistoryStore
from app.uploads import MAX_REQUEST_BYTES, save_image
from app.jobs import JobQueue, QueueFull
from app.evaluation import held_out_hashes
from app.file_lock import file_lock, ResourceBusy
from app.ai.pipeline import run_integrity_pipeline

try:
    from env_loader import load_project_env
except ModuleNotFoundError:  # pragma: no cover - supports python -m app.web_alteracao
    from app.env_loader import load_project_env

load_project_env()

try:
    from local_forensics import (
        ForensicResult,
        analyze_forensics,
        build_calibration_samples,
        compare_with_original,
        comparison_feature_profile,
        feature_profile_from_metrics,
        file_sha256 as forensic_sha256,
        local_metrics,
    )
except ModuleNotFoundError:  # pragma: no cover - supports python -m app.web_alteracao
    from app.local_forensics import (
        ForensicResult,
        analyze_forensics,
        build_calibration_samples,
        compare_with_original,
        comparison_feature_profile,
        feature_profile_from_metrics,
        file_sha256 as forensic_sha256,
        local_metrics,
    )

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - fallback for minimal installs
    Image = None
    ImageOps = None


PORT = int(os.environ.get("WEB_PORT", "9090"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
MODEL = os.environ.get("VISION_MODEL", "codex-dental:latest")
AI_SETTINGS = get_settings()
LLM_PROVIDER = AI_SETTINGS.provider
GEMINI_MODEL = AI_SETTINGS.model
DEVELOPMENT_MODE = AI_SETTINGS.development
HISTORY_LOCK = RLock()
JOB_QUEUE = None
JOB_LOCK = RLock()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
ANALYSIS_DIR = RUNTIME_DIR / "analysis_cache"
HISTORY_FILE = RUNTIME_DIR / "analysis_history.json"
CALIBRATION_FILE = RUNTIME_DIR / "integrity_calibration.json"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
HISTORY_PAGE_SIZE = int(os.environ.get("HISTORY_PAGE_SIZE", "8"))
ANALYSIS_MAX_SIDE = int(os.environ.get("ANALYSIS_MAX_SIDE", "896"))
TESTS_DIR = PROJECT_ROOT / "tests"

MODEL_OPTIONS = {
    "temperature": 0.1,
    "num_ctx": 896,
    "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "48")),
    "num_thread": int(os.environ.get("OLLAMA_NUM_THREAD", "0")) or None,
}
MODEL_OPTIONS = {key: value for key, value in MODEL_OPTIONS.items() if value is not None}
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
DEFAULT_ESTIMATED_SECONDS = float(os.environ.get("DEFAULT_ESTIMATED_SECONDS", "8"))
FAST_LOCAL_MODE = os.environ.get("FAST_LOCAL_MODE", "1").lower() not in {"0", "false", "nao", "não"}

STATIC_DIR = Path(__file__).resolve().parent / "static"
HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def clean_model_response(text: object) -> str:
    value = str(text)
    if "<unused95>" in value:
        value = value.rsplit("<unused95>", 1)[-1]
    value = re.sub(r"<unused94>\s*thought.*?<unused95>", "", value, flags=re.DOTALL)
    value = value.replace("<unused94>", "").replace("<unused95>", "")
    value = re.sub(r"(?is)\n?\s*thought\s*\n.*$", "", value)
    value = re.sub(r"(?is)^.*?(VEREDITO\s*:)", r"\1", value)
    allowed_lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(
            r"^(VEREDITO|TIPO|CONFIANCA|SCORE|SCORE_ALTERACAO|JUSTIFICATIVA|EVIDENCIAS)\s*:",
            stripped,
            re.I,
        ):
            allowed_lines.append(stripped)
    return "\n".join(allowed_lines).strip() or value.strip()


def infer_verdict(report: str) -> str:
    normalized = report.upper()
    label_match = re.search(
        r"\bVEREDITO\s*:\s*(REAL|MODIFICADO|ALTERADA[_ ]MANUALMENTE|ALTERADA[_ ]DIGITALMENTE|IA(?:[_ ]GERADA[_/]?EDITADA)?|INDETERMINADO)\b",
        normalized,
    )
    if label_match:
        value = label_match.group(1).replace(" ", "_")
        return "IA_GERADA_EDITADA" if value == "IA" else value
    match = re.search(r"\bVEREDITO\s*:\s*(SIM|NAO|NÃO|INDETERMINADO)\b", normalized)
    if match:
        value = match.group(1)
        return "NAO" if value == "NÃO" else value
    if re.search(r"\bSIM\b", normalized[:160]):
        return "SIM"
    if re.search(r"\bNAO\b|\bNÃO\b", normalized[:160]):
        return "NAO"
    return "INDETERMINADO"


def canonical_integrity_label(value: str) -> str:
    normalized = value.upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "NAO": "REAL",
        "NÃO": "REAL",
        "SIM": "MODIFICADO",
        "ALTERADA": "MODIFICADO",
        "ALTERADA_MANUALMENTE": "MODIFICADO",
        "ALTERADA_DIGITALMENTE": "MODIFICADO",
        "IA": "IA_GERADA_EDITADA",
        "IA_GERADA": "IA_GERADA_EDITADA",
        "IA_EDITADA": "IA_GERADA_EDITADA",
        "IA_GERADA/EDITADA": "IA_GERADA_EDITADA",
        "ALTERADA_MANUAL": "MODIFICADO",
        "ALTERADA_DIGITAL": "MODIFICADO",
    }
    normalized = aliases.get(normalized, normalized)
    valid = {
        "REAL",
        "MODIFICADO",
        "ALTERADA_MANUALMENTE",
        "ALTERADA_DIGITALMENTE",
        "IA_GERADA_EDITADA",
        "INDETERMINADO",
    }
    return normalized if normalized in valid else "INDETERMINADO"


def infer_score(report: str) -> int | None:
    match = re.search(r"\bSCORE(?:_ALTERACAO)?\s*:\s*(\d{1,3})\b", report, re.I)
    if not match:
        return None
    return max(0, min(int(match.group(1)), 100))


def verdict_from_score(score: int | None, fallback: str) -> str:
    fallback = canonical_integrity_label(fallback)
    if score is None:
        return fallback
    if score <= 29:
        return "REAL"
    if score <= 59:
        return "INDETERMINADO"
    if score <= 79:
        return fallback if fallback in {"MODIFICADO", "ALTERADA_MANUALMENTE", "ALTERADA_DIGITALMENTE"} else "MODIFICADO"
    return fallback if fallback not in {"REAL", "INDETERMINADO"} else "IA_GERADA_EDITADA"


def confidence_from_score(score: int | None, verdict: str) -> str:
    if score is None:
        return "media" if verdict != "INDETERMINADO" else "baixa"
    if verdict == "INDETERMINADO":
        return "media" if 40 <= score <= 60 else "baixa"
    distance = min(abs(score - 29), abs(score - 70))
    if distance >= 25:
        return "alta"
    if distance >= 10:
        return "media"
    return "baixa"


def get_field(report: str, field: str) -> str:
    match = re.search(rf"^{field}\s*:\s*(.+)$", report, re.I | re.M)
    return match.group(1).strip() if match else ""


def confidence_label_from_percent(value: object) -> str:
    match = re.search(r"\d{1,3}", str(value or ""))
    if not match:
        return "media"
    percent = max(0, min(int(match.group(0)), 100))
    if percent >= 80:
        return "alta"
    if percent >= 55:
        return "media"
    return "baixa"


def score_default_for_verdict(verdict: str) -> int:
    verdict = canonical_integrity_label(verdict)
    if verdict == "REAL":
        return 15
    if verdict == "INDETERMINADO":
        return 50
    if verdict == "MODIFICADO":
        return 80
    return 88


def extract_json_object(text: object) -> dict[str, Any] | None:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I).strip()
    value = re.sub(r"\s*```$", "", value).strip()
    candidates = [value]
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def report_from_gemini_json(parsed: dict[str, Any]) -> str:
    verdict_value = parsed.get("veredito_revisado", parsed.get("veredito", "INDETERMINADO"))
    verdict = canonical_integrity_label(str(verdict_value))
    score_value = parsed.get("score_alteracao")
    try:
        score = max(0, min(int(str(score_value).replace("%", "").strip()), 100))
    except (TypeError, ValueError):
        score = score_default_for_verdict(verdict)
    invalidar_laudo = str(parsed.get("invalidar_laudo", "false")).strip().lower() in {
        "1",
        "true",
        "sim",
        "yes",
    }
    quality_value = str(parsed.get("qualidade_imagem", "")).strip().lower()
    if invalidar_laudo and verdict == "REAL":
        verdict = "MODIFICADO"
        score = max(score, 80)
    if quality_value == "insuficiente" and verdict == "REAL":
        verdict = "INDETERMINADO"
        score = max(score, 50)
    confidence = confidence_label_from_percent(parsed.get("confianca"))
    evidence_value = parsed.get("evidencias_visuais", [])
    if isinstance(evidence_value, list):
        evidences = "; ".join(str(item).strip() for item in evidence_value if str(item).strip())
    else:
        evidences = str(evidence_value or "").strip()
    scale = parsed.get("analise_escala", {})
    if isinstance(scale, dict):
        scale_notes = "; ".join(
            f"{key}: {value}" for key, value in scale.items() if str(value).strip()
        )
    else:
        scale_notes = str(scale or "").strip()
    if scale_notes:
        evidences = f"{evidences}; analise visual multiescala: {scale_notes}" if evidences else scale_notes
    artifacts = parsed.get("artefatos_ia", [])
    if isinstance(artifacts, list):
        artifact_notes = "; ".join(str(item).strip() for item in artifacts if str(item).strip())
    else:
        artifact_notes = str(artifacts or "").strip()
    if artifact_notes:
        evidences = f"{evidences}; artefatos IA avaliados: {artifact_notes}" if evidences else artifact_notes
    audit_note = str(parsed.get("auditoria_clinica", "")).strip()
    if audit_note:
        evidences = f"{evidences}; auditoria clinica: {audit_note}" if evidences else f"auditoria clinica: {audit_note}"
    conflicts = parsed.get("conflitos_forenses", [])
    if isinstance(conflicts, list):
        conflict_notes = "; ".join(str(item).strip() for item in conflicts if str(item).strip())
    else:
        conflict_notes = str(conflicts or "").strip()
    if conflict_notes:
        evidences = f"{evidences}; conflitos forenses: {conflict_notes}" if evidences else f"conflitos forenses: {conflict_notes}"
    revision_note = str(parsed.get("motivo_revisao", "")).strip()
    if revision_note:
        evidences = f"{evidences}; motivo da revisao: {revision_note}" if evidences else f"motivo da revisao: {revision_note}"
    if quality_value:
        evidences = f"{evidences}; qualidade da imagem: {quality_value}" if evidences else f"qualidade da imagem: {quality_value}"
    if invalidar_laudo:
        evidences = f"{evidences}; integridade primeiro: laudo clinico invalidado pela analise de integridade"
    if not evidences:
        evidences = "sem evidencias adicionais informadas"

    if verdict == "REAL":
        justification = "A analise combinada nao encontrou sinais fortes de manipulacao visual."
    elif verdict == "MODIFICADO":
        justification = "A analise combinada encontrou sinais visuais compativeis com modificacao."
    elif verdict == "IA_GERADA_EDITADA":
        justification = "A analise combinada encontrou sinais visuais compativeis com edicao ou geracao por IA."
    else:
        justification = "A imagem apresenta evidencias visuais insuficientes ou conflitantes."

    disclaimer = str(parsed.get("disclaimer_itu", "")).strip()
    if disclaimer:
        evidences = f"{evidences}; {disclaimer}"

    return "\n".join(
        [
            f"VEREDITO: {verdict}",
            f"CONFIANCA: {confidence}",
            f"JUSTIFICATIVA: {justification}",
            f"TIPO: {verdict if verdict != 'IA_GERADA_EDITADA' else 'IA'}",
            f"SCORE_ALTERACAO: {score}",
            f"EVIDENCIAS: {evidences}",
        ]
    )


def normalize_llm_response(text: object) -> str:
    parsed = extract_json_object(text)
    if parsed is not None:
        return report_from_gemini_json(parsed)
    return clean_model_response(text)


def report_with_extra_evidence(report: str, extra: str) -> dict[str, str]:
    normalized = normalize_report(report)
    if not extra.strip():
        return normalized
    lines = normalized["report"].splitlines()
    updated_lines: list[str] = []
    added = False
    for line in lines:
        if line.upper().startswith("EVIDENCIAS:"):
            updated_lines.append(f"{line}; {extra}")
            added = True
        else:
            updated_lines.append(line)
    if not added:
        updated_lines.append(f"EVIDENCIAS: {extra}")
    final_report = "\n".join(updated_lines)
    return {"verdict": normalize_report(final_report)["verdict"], "report": final_report}


def normalize_report(report: str) -> dict[str, str]:
    score = infer_score(report)
    verdict = verdict_from_score(score, infer_verdict(report))
    confidence = get_field(report, "CONFIANCA") or confidence_from_score(score, verdict)
    justification = get_field(report, "JUSTIFICATIVA")
    if not justification:
        if verdict == "REAL":
            justification = "A imagem apresenta anatomia coerente, reflexos compatíveis e ausencia de bordas artificiais."
        elif verdict == "MODIFICADO":
            justification = "A imagem apresenta sinais de modificacao visual sobreposta ou edicao."
        elif verdict == "ALTERADA_MANUALMENTE":
            justification = "A imagem apresenta marcacoes, esbocos, textos ou anotacoes sobrepostas."
        elif verdict == "ALTERADA_DIGITALMENTE":
            justification = "A imagem apresenta sinais de borroes, recortes, colagens ou edicao de software."
        elif verdict == "IA_GERADA_EDITADA":
            justification = "A imagem apresenta sinais de geracao ou edicao por IA, como anatomia ou textura nao biologica."
        else:
            justification = "A imagem apresenta evidencias insuficientes para classificar a integridade com seguranca."
    tipo = get_field(report, "TIPO") or verdict
    evidencias = get_field(report, "EVIDENCIAS") or "sem evidencias adicionais informadas"
    score_text = str(score if score is not None else (15 if verdict == "REAL" else 50 if verdict == "INDETERMINADO" else 80))
    normalized_report = "\n".join(
        [
            f"VEREDITO: {verdict}",
            f"CONFIANCA: {confidence}",
            f"JUSTIFICATIVA: {justification}",
            f"TIPO: {tipo}",
            f"SCORE_ALTERACAO: {score_text}",
            f"EVIDENCIAS: {evidencias}",
        ]
    )
    return {"verdict": verdict, "report": normalized_report}


def report_from_forensics(forensic: ForensicResult) -> dict[str, str]:
    verdict = canonical_integrity_label(forensic.verdict_hint)
    evidence = "; ".join(forensic.evidence[:5]) or "sem evidencias locais fortes"
    quality_status = str(forensic.metrics.get("quality_status", ""))
    quality_insufficient = verdict == "INDETERMINADO" and quality_status == "insuficiente"
    if forensic.calibration_entry:
        justification = str(forensic.calibration_entry.get("justification", "")).strip()
    else:
        justification = ""
    if not justification:
        if quality_insufficient:
            justification = "Imagem com resolucao/nitidez insuficiente para pericia visual confiavel."
        elif verdict == "REAL":
            justification = "A imagem apresenta baixa pontuacao local de alteracao e sinais visuais coerentes."
        elif verdict == "IA_GERADA_EDITADA":
            justification = "A imagem apresenta sinais locais fortes compativeis com edicao ou geracao por IA."
        elif verdict == "MODIFICADO":
            justification = "A imagem apresenta modificacao visual detectada, como linha, seta, desenho ou anotacao sobreposta."
        elif verdict == "ALTERADA_DIGITALMENTE":
            justification = "A imagem apresenta sinais locais compativeis com edicao digital."
        elif verdict == "ALTERADA_MANUALMENTE":
            justification = "A imagem apresenta sinais locais compativeis com marcacao ou sobreposicao manual."
        else:
            justification = "A imagem apresenta sinais locais intermediarios ou conflitantes."
    report = "\n".join(
        [
            f"VEREDITO: {verdict}",
            f"CONFIANCA: {forensic.confidence}",
            f"JUSTIFICATIVA: {justification}",
            f"TIPO: {'QUALIDADE_INSUFICIENTE' if quality_insufficient else verdict if verdict != 'IA_GERADA_EDITADA' else 'IA'}",
            f"SCORE_ALTERACAO: {forensic.score}",
            f"EVIDENCIAS: {evidence}",
        ]
    )
    return {"verdict": verdict, "report": report}


def has_local_inconsistency(forensic: ForensicResult) -> bool:
    metrics = forensic.metrics
    return any(
        [
            float(metrics.get("ela_block_cv", 0) or 0) >= 0.35 and float(metrics.get("ela_p95", 0) or 0) >= 5,
            float(metrics.get("noise_block_cv", 0) or 0) >= 0.60,
            float(metrics.get("sharpness_block_cv", 0) or 0) >= 0.75,
            bool(metrics.get("comparison")),
            bool(metrics.get("nearest_pattern")),
            bool(metrics.get("nearest_pair_pattern")),
        ]
    )


def should_run_clinical_audit(initial_report: str, forensic: ForensicResult) -> bool:
    if str(forensic.metrics.get("quality_status", "")) == "insuficiente":
        return False
    initial = normalize_report(initial_report)
    initial_verdict = canonical_integrity_label(initial["verdict"])
    modified_labels = {"MODIFICADO", "ALTERADA_MANUALMENTE", "ALTERADA_DIGITALMENTE", "IA_GERADA_EDITADA"}
    if initial_verdict in modified_labels:
        return True
    if initial_verdict == "REAL":
        return (
            forensic.score >= 30
            or str(forensic.metrics.get("quality_status", "")) == "limitada"
            or has_local_inconsistency(forensic)
        )
    return forensic.score >= 30 or has_local_inconsistency(forensic)


def parsed_audit_conflict(raw_response: object) -> bool:
    parsed = extract_json_object(raw_response)
    if not parsed:
        return False
    if str(parsed.get("invalidar_laudo", "false")).strip().lower() in {"1", "true", "sim", "yes"}:
        return True
    conflicts = parsed.get("conflitos_forenses", [])
    if isinstance(conflicts, list):
        text = " ".join(str(item).lower() for item in conflicts)
    else:
        text = str(conflicts or "").lower()
    if not text.strip():
        return False
    benign_markers = {"sem conflito", "nenhum conflito", "nao ha conflito", "sem divergencia"}
    return not any(marker in text for marker in benign_markers)


def audit_evidence_from_response(raw_response: object, audit_report: str = "") -> list[str]:
    parsed = extract_json_object(raw_response)
    evidence: list[str] = []
    if isinstance(parsed, dict):
        for key in ("auditoria_clinica", "motivo_revisao"):
            value = str(parsed.get(key, "")).strip()
            if value:
                evidence.append(value)
        conflicts = parsed.get("conflitos_forenses", [])
        if isinstance(conflicts, list):
            evidence.extend(str(item).strip() for item in conflicts if str(item).strip())
        elif str(conflicts or "").strip():
            evidence.append(str(conflicts).strip())
    if not evidence:
        report_evidence = get_field(audit_report, "EVIDENCIAS")
        if report_evidence:
            evidence.append(report_evidence)
    return evidence[:5]


def merge_llm_and_forensics(llm_report: str, forensic: ForensicResult) -> dict[str, str]:
    llm_normalized = normalize_report(llm_report)
    llm_score = infer_score(llm_normalized["report"])
    local_score = forensic.score
    local_preferred = canonical_integrity_label(forensic.verdict_hint)
    modified_labels = {"MODIFICADO", "ALTERADA_MANUALMENTE", "ALTERADA_DIGITALMENTE", "IA_GERADA_EDITADA"}
    quality_status = str(forensic.metrics.get("quality_status", ""))

    if quality_status == "insuficiente" and local_preferred not in modified_labels and local_score < 60:
        return report_from_forensics(forensic)

    if local_score <= 18 or local_score >= 82 or (local_preferred in modified_labels and local_score >= 60):
        return report_from_forensics(forensic)

    if llm_score is None:
        final_score = local_score
    elif forensic.original_used:
        if local_score >= 80 or local_score <= 20:
            final_score = local_score
        else:
            final_score = round((local_score * 0.7) + (llm_score * 0.3))
    else:
        final_score = round((local_score * 0.55) + (llm_score * 0.45))

    llm_preferred = infer_verdict(llm_normalized["report"])
    preferred = local_preferred if local_score >= 60 or local_score <= 29 else llm_preferred
    verdict = verdict_from_score(final_score, preferred)
    confidence = confidence_from_score(final_score, verdict)

    llm_justification = get_field(llm_normalized["report"], "JUSTIFICATIVA")
    local_evidence = "; ".join(forensic.evidence[:4])
    llm_evidence = get_field(llm_normalized["report"], "EVIDENCIAS")
    if verdict == "REAL":
        justification = "A imagem apresenta baixa pontuacao local de alteracao e nao ha evidencias fortes de manipulacao."
    elif forensic.original_used and final_score >= 60:
        justification = "A comparacao com a imagem original mostra diferencas relevantes nas regioes analisadas."
    else:
        justification = llm_justification or "A classificacao combina sinais locais e leitura visual da LLM."

    report = "\n".join(
        [
            f"VEREDITO: {verdict}",
            f"CONFIANCA: {confidence}",
            f"JUSTIFICATIVA: {justification}",
            f"TIPO: {verdict if verdict != 'IA_GERADA_EDITADA' else 'IA'}",
            f"SCORE_ALTERACAO: {final_score}",
            f"EVIDENCIAS: {local_evidence}; LLM: {llm_evidence or 'sem evidencia adicional'}",
        ]
    )
    return {"verdict": verdict, "report": report}


def integrity_report(verdict: str, score: int, confidence: str, justification: str, evidence: str) -> dict[str, str]:
    verdict = canonical_integrity_label(verdict)
    report = "\n".join(
        [
            f"VEREDITO: {verdict}",
            f"CONFIANCA: {confidence}",
            f"JUSTIFICATIVA: {justification}",
            f"TIPO: {verdict if verdict != 'IA_GERADA_EDITADA' else 'IA'}",
            f"SCORE_ALTERACAO: {max(0, min(int(score), 100))}",
            f"EVIDENCIAS: {evidence}",
        ]
    )
    return normalize_report(report)


def merge_audit_and_forensics(
    initial_report: str,
    audit_result: dict[str, Any],
    forensic: ForensicResult,
) -> dict[str, str]:
    status = str(audit_result.get("audit_status") or "nao_executada")
    if status == "executada" and audit_result.get("audit_report"):
        audit_report = str(audit_result["audit_report"])
        merged = merge_llm_and_forensics(audit_report, forensic)
        audit_normalized = normalize_report(audit_report)
        audit_verdict = canonical_integrity_label(audit_normalized["verdict"])
        audit_score = infer_score(audit_normalized["report"]) or forensic.score
        audit_evidence = "; ".join(audit_result.get("audit_evidence") or [])

        if audit_verdict == "IA_GERADA_EDITADA" and forensic.score >= 50:
            return integrity_report(
                "IA_GERADA_EDITADA",
                max(80, audit_score, forensic.score),
                confidence_from_score(max(80, audit_score, forensic.score), "IA_GERADA_EDITADA"),
                "A auditoria CRAG confirmou sinais compativeis com edicao ou geracao por IA apoiados pela pericia local.",
                f"{audit_evidence or get_field(audit_normalized['report'], 'EVIDENCIAS')}; Auditoria CRAG: veredito elevado para IA_GERADA_EDITADA",
            )

        if audit_result.get("audit_conflict") and merged["verdict"] in {"REAL", "INDETERMINADO"}:
            if max(audit_score, forensic.score) >= 60:
                return integrity_report(
                    "MODIFICADO",
                    max(60, audit_score, forensic.score),
                    "media",
                    "A auditoria CRAG encontrou conflito entre achado visual e sinais forenses locais.",
                    f"{audit_evidence or 'conflito forense detectado'}; Auditoria CRAG: conflito impediu veredito REAL",
                )
            return integrity_report(
                "INDETERMINADO",
                max(50, audit_score, forensic.score),
                "baixa",
                "A auditoria CRAG encontrou conflito insuficiente para confirmar integridade ou modificacao.",
                f"{audit_evidence or 'conflito forense detectado'}; Auditoria CRAG: veredito REAL bloqueado",
            )

        extra = f"Auditoria CRAG: {status}"
        if audit_evidence:
            extra = f"{extra}; {audit_evidence}"
        return report_with_extra_evidence(merged["report"], extra)

    merged = merge_llm_and_forensics(initial_report, forensic)
    if status == "falhou":
        evidence = "; ".join(audit_result.get("audit_evidence") or ["auditoria CRAG falhou"])
        return report_with_extra_evidence(merged["report"], f"Auditoria CRAG: falhou; {evidence}")
    return merged


def normalize_history_item(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("schema_version") == "2.0":
        return dict(item)
    cleaned = dict(item)
    report = str(cleaned.get("report") or "")
    cleaned["report"] = report or "Relatorio legado indisponivel."
    if not cleaned.get("verdict"):
        cleaned["verdict"] = get_field(report, "VEREDITO") or None
    if cleaned.get("source") is None:
        cleaned["source"] = "historico_legado"
    if cleaned.get("forensic_evidence") is None:
        evidence = get_field(report, "EVIDENCIAS")
        cleaned["forensic_evidence"] = [evidence] if evidence else []
    if cleaned.get("forensic_quality") is None:
        metrics = cleaned.get("forensic_metrics")
        if isinstance(metrics, dict):
            cleaned["forensic_quality"] = metrics.get("quality_status")
    if cleaned.get("audit_status") is None:
        cleaned["audit_status"] = "nao_executada"
    if cleaned.get("audit_evidence") is None:
        cleaned["audit_evidence"] = []
    return cleaned


def history_store() -> HistoryStore:
    return HistoryStore(HISTORY_FILE.with_suffix(".sqlite3"), HISTORY_FILE)


def load_history() -> list[dict[str, Any]]:
    return [normalize_history_item(item) for item in history_store().all()]



def history_is_modified(item: dict[str, Any]) -> bool:
    verdict = str(item.get("verdict") or "").upper()
    return any(token in verdict for token in ("MODIFICADO", "ALTERADA", "IA", "EDICAO"))


def history_is_calibration(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or "").lower()
    model = str(item.get("model") or "").lower()
    return "calibracao" in source or "feedback" in source or "calibracao" in model


def history_matches_tab(item: dict[str, Any], tab: str) -> bool:
    verdict = str(item.get("verdict") or "").upper()
    if tab == "modified":
        return history_is_modified(item)
    if tab == "real":
        return verdict == "REAL"
    if tab == "inconclusive":
        return verdict == "INDETERMINADO" or item.get("status") == "nao_concluida"
    if tab == "calibration":
        return history_is_calibration(item)
    return True


def history_tab_counts(history: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "all": len(history),
        "modified": sum(1 for item in history if history_is_modified(item)),
        "real": sum(1 for item in history if str(item.get("verdict") or "").upper() == "REAL"),
        "inconclusive": sum(1 for item in history if str(item.get("verdict") or "").upper() == "INDETERMINADO"),
        "calibration": sum(1 for item in history if history_is_calibration(item)),
    }


def paginated_history(tab: str, page: int, page_size: int = HISTORY_PAGE_SIZE, model: str = "") -> dict[str, Any]:
    valid_tabs = {"all", "modified", "real", "inconclusive", "calibration"}
    tab = tab if tab in valid_tabs else "all"
    history = load_history()
    counts = history_tab_counts(history)
    filtered = [item for item in history if history_matches_tab(item, tab) and (not model or item.get("model") == model)]
    total = len(filtered)
    page_size = max(1, min(int(page_size), 50))
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start_index = (page - 1) * page_size
    end_index = min(start_index + page_size, total)
    return {
        "history": filtered[start_index:end_index],
        "models": sorted({str(item["model"]) for item in history if item.get("model")}),
        "pagination": {
            "tab": tab,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_all": len(history),
            "total_pages": total_pages,
            "start": start_index + 1 if total else 0,
            "end": end_index,
            "counts": counts,
        },
    }


def file_sha256(path: Path) -> str:
    return forensic_sha256(path)


def load_calibration() -> dict[str, Any]:
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def calibration_rag_examples(limit: int = 3) -> str:
    calibration = load_calibration()
    if not calibration:
        return "Nenhum exemplo previo disponivel."
    examples: list[dict[str, Any]] = []
    for sha256, entry in list(calibration.items())[-limit:]:
        if not isinstance(entry, dict):
            continue
        compact = {
            "sha256_prefix": str(sha256)[:12],
            "label": entry.get("label"),
            "score": entry.get("score"),
            "evidence": entry.get("evidence"),
            "justification": entry.get("justification"),
            "stored_filename": entry.get("stored_filename"),
        }
        if isinstance(entry.get("comparison"), dict):
            comparison = entry["comparison"]
            compact["comparison"] = {
                "same_scene": comparison.get("same_scene"),
                "central_mean_diff": comparison.get("central_mean_diff"),
                "central_high_diff_ratio": comparison.get("central_high_diff_ratio"),
            }
        examples.append(compact)
    return json.dumps(examples or "Nenhum exemplo previo disponivel.", ensure_ascii=False)


def compact_forensic_payload(forensic: ForensicResult) -> str:
    metric_keys = [
        "ela_mean",
        "ela_p95",
        "ela_block_cv",
        "image_width",
        "image_height",
        "image_megapixels",
        "image_min_side",
        "quality_status",
        "quality_reasons",
        "blur_level",
        "laplacian_var",
        "sharpness_block_cv",
        "noise_mean",
        "noise_block_cv",
        "saturated_overlay_ratio",
        "marker_overlay_ratio",
        "green_marker_ratio",
        "red_marker_ratio",
        "blue_marker_ratio",
        "overlay_regions",
        "nearest_calibration_distance",
        "comparison",
        "nearest_pattern",
        "nearest_pair_pattern",
    ]
    payload = {
        "score_local": forensic.score,
        "veredito_local": forensic.verdict_hint,
        "fonte_local": forensic.source,
        "original_usada": forensic.original_used,
        "evidencias_locais": forensic.evidence,
        "metricas": {
            key: forensic.metrics.get(key)
            for key in metric_keys
            if key in forensic.metrics
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def save_calibration(calibration: dict[str, Any]) -> None:
    CALIBRATION_FILE.write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_calibration_samples():
    return build_calibration_samples(
        load_calibration(),
        [UPLOAD_DIR, TESTS_DIR],
    )


def calibrated_result(image_path: Path) -> dict[str, str] | None:
    calibration = load_calibration()
    entry = calibration.get(file_sha256(image_path))
    if not isinstance(entry, dict):
        return None
    report = "\n".join(
        [
            f"VEREDITO: {entry.get('label', 'INDETERMINADO')}",
            f"CONFIANCA: {entry.get('confidence', 'alta')}",
            f"JUSTIFICATIVA: {entry.get('justification', '')}",
            f"TIPO: {entry.get('type', 'INDETERMINADO')}",
            f"SCORE_ALTERACAO: {entry.get('score', 50)}",
            f"EVIDENCIAS: {entry.get('evidence', '')}",
        ]
    )
    normalized = normalize_report(report)
    return {
        "verdict": normalized["verdict"],
        "report": normalized["report"],
        "duration_seconds": "0.01",
        "source": "calibracao_local",
    }


def estimated_analysis_seconds() -> float:
    durations: list[float] = []
    for item in load_history()[:20]:
        try:
            value = float(item.get("duration_seconds", 0))
        except (TypeError, ValueError):
            continue
        if 3 <= value <= 240:
            durations.append(value)
    if not durations:
        return DEFAULT_ESTIMATED_SECONDS
    durations.sort()
    midpoint = len(durations) // 2
    if len(durations) % 2:
        return durations[midpoint]
    return (durations[midpoint - 1] + durations[midpoint]) / 2


def ollama_is_available() -> bool:
    try:
        base_url = OLLAMA_HOST
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        with urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=1.5) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def model_catalog() -> dict[str, Any]:
    descriptors = [{"provider": "gemini", "model": model, "vision": True, "loaded": None,
                    "server": "Google Gemini API", "configured": bool(AI_SETTINGS.api_key)} for model in SUPPORTED_MODELS]
    catalog = {"models": list(SUPPORTED_MODELS), "local_models": [], "lmstudio_status": "", "catalog": descriptors}
    if not DEVELOPMENT_MODE:
        catalog["lmstudio_status"] = "Modelos locais exigem modo de desenvolvimento."
    else:
        try:
            local = lmstudio_client.model_descriptors()
            descriptors.extend(local)
            catalog["local_models"] = [model["model"] for model in local if model["loaded"] and model["vision"] is True]
            catalog["lmstudio_status"] = "LM Studio conectado" if catalog["local_models"] else "LM Studio: nenhum modelo visual carregado."
        except Exception:
            catalog["lmstudio_status"] = "LM Studio indisponivel. Verifique o servidor e LM_STUDIO_HOST."
    for descriptor in descriptors:
        name = descriptor["provider"] + '-' + ''.join(c if c.isalnum() or c in '-_' else '_' for c in descriptor["model"]) + '.json'
        check = RUNTIME_DIR / 'provider_checks' / name
        if check.is_file():
            try:
                descriptor['last_check'] = json.loads(check.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
    return catalog


def available_agents() -> list[dict[str, Any]]:
    gemini_ready = bool(AI_SETTINGS.api_key)
    ollama_ready = ollama_is_available() if DEVELOPMENT_MODE else False
    agents = [
        {
            "provider": "local",
            "name": "Pericia local rapida",
            "available": True,
            "detail": "Sempre disponivel; usa metricas locais, calibracao e comparacao.",
            "mode": "local",
        },
        {
            "provider": "gemini",
            "name": f"Gemini detalhado ({GEMINI_MODEL})",
            "available": gemini_ready,
            "detail": "Chave configurada; disponibilidade do modelo confirmada apenas ao executar a analise.",
            "state": "configurado" if gemini_ready else "sem chave",
            "mode": "llm",
        },
        {
            "provider": "ollama",
            "name": f"Ollama local ({MODEL})",
            "available": ollama_ready,
            "detail": f"Verifica {OLLAMA_HOST}; use para analise local detalhada.",
            "mode": "llm",
        },
    ]
    return agents if DEVELOPMENT_MODE else [agent for agent in agents if agent["provider"] == "gemini"]


def save_history(history: list[dict[str, Any]]) -> None:
    history_store().upsert_all(history)


def append_history(entry: dict[str, Any]) -> None:
    history_store().append(entry)



def calibration_entry_for_label(label: str) -> dict[str, Any]:
    normalized = canonical_integrity_label(label)
    if normalized == "REAL":
        return {
            "label": "REAL",
            "confidence": "alta",
            "score": 8,
            "type": "REAL",
            "evidence": "perfil visual informado pelo usuario como imagem real/original",
            "justification": "A imagem foi marcada pelo usuario como exemplo real para aprendizado local de padrao.",
        }
    if normalized == "IA_GERADA_EDITADA":
        return {
            "label": "IA_GERADA_EDITADA",
            "confidence": "alta",
            "score": 92,
            "type": "IA",
            "evidence": "rotulo informado pelo usuario como imagem alterada/gerada por IA",
            "justification": "A imagem foi marcada pelo usuario como exemplo de edicao ou geracao por IA.",
        }
    return {
        "label": "MODIFICADO",
        "confidence": "alta",
        "score": 90,
        "type": "MODIFICADO",
        "evidence": "perfil visual informado pelo usuario como imagem modificada/falsa",
        "justification": "A imagem foi marcada pelo usuario como exemplo modificado para aprendizado local de padrao.",
    }


def calibrated_feedback_result(label: str) -> dict[str, Any]:
    entry = calibration_entry_for_label(label)
    report = "\n".join(
        [
            f"VEREDITO: {entry['label']}",
            f"CONFIANCA: {entry['confidence']}",
            f"JUSTIFICATIVA: {entry['justification']}",
            f"TIPO: {entry['type']}",
            f"SCORE_ALTERACAO: {entry['score']}",
            f"EVIDENCIAS: {entry['evidence']}",
        ]
    )
    normalized = normalize_report(report)
    return {
        "verdict": normalized["verdict"],
        "report": normalized["report"],
        "duration_seconds": "0.01",
        "source": "feedback_usuario",
        "forensic_score": entry["score"],
        "forensic_evidence": [entry["evidence"]],
        "forensic_metrics": {},
        "calibration_entry": entry,
    }


def prepare_analysis_image(image_path: Path) -> Path:
    if Image is None or ImageOps is None:
        return image_path

    ANALYSIS_DIR.mkdir(exist_ok=True)
    optimized_path = ANALYSIS_DIR / f"{image_path.stem}_fast.jpg"
    try:
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((ANALYSIS_MAX_SIDE, ANALYSIS_MAX_SIDE))
            image.save(
                optimized_path,
                format="JPEG",
                quality=82,
                optimize=True,
                progressive=False,
            )
    except Exception:
        return image_path
    return optimized_path


def call_gemini_flash(prompt: str, image_path: Path, max_output_tokens: int = 256) -> tuple[str, str]:
    if not DEVELOPMENT_MODE:
        raise RuntimeError("Chamadas livres ao Gemini sao exclusivas do modo de desenvolvimento.")
    generated = GeminiClient(AI_SETTINGS).generate(
        prompt, "Ferramenta experimental de integridade visual. Nao emita diagnostico.",
        image_path, max_output_tokens=max_output_tokens,
    )
    return generated.text, generated.requested_model


def call_ollama_llm(prompt: str, image_path: Path) -> str:
    client = ollama.Client(host=OLLAMA_HOST)
    response = client.generate(
        model=MODEL,
        prompt=prompt,
        images=[str(image_path)],
        options=MODEL_OPTIONS,
        keep_alive=KEEP_ALIVE,
    )
    return str(response["response"])


def call_detailed_llm(prompt: str, image_path: Path, provider: str | None = None) -> tuple[str, str, str]:
    provider = (provider or LLM_PROVIDER or "gemini").strip().lower()
    if provider == "ollama":
        return call_ollama_llm(prompt, image_path), "hibrido_local_ollama", MODEL
    if provider not in {"gemini", "google", "gemini_flash"}:
        raise RuntimeError("LLM_PROVIDER invalido. Use gemini ou ollama.")
    response_text, model_name = call_gemini_flash(prompt, image_path)
    return response_text, "hibrido_local_gemini", model_name


def build_advanced_codex_prompt(forensic: ForensicResult) -> str:
    local_forensics_data = compact_forensic_payload(forensic)
    exemplos_rag = calibration_rag_examples(limit=3)
    return f"""
VOCE E O PERITO VISUAL SENIOR DO MODULO CODEX.

IMPORTANTE:
- Nao emita diagnostico odontologico.
- Descreva apenas achados visuais de integridade, alteracao e compatibilidade aparente.
- Integridade vem antes de qualquer leitura clinica: se a imagem for fraudada, modificada ou tiver qualidade insuficiente, invalide qualquer conclusao clinica.
- A decisao final e suporte tecnico; a responsabilidade clinica e do cirurgiao-dentista.

DADOS DA PERICIA LOCAL (ELA, dHash, ruido, comparacao e marcadores):
{local_forensics_data}

EXEMPLOS CALIBRADOS DO PROJETO LOCAL (RAG / verdade operacional):
{exemplos_rag}

SUA TAREFA:
1. ANALISE DE INTEGRIDADE FORENSE:
   - Classifique como REAL, MODIFICADO, IA_GERADA_EDITADA ou INDETERMINADO.
   - Procure setas, linhas, esbocos, textos, recortes, halos, borroes, colagem e sinais de IA.
   - Em fotos intraorais, procure dentes fundidos, textura gengival artificial, esmalte plastificado e contornos nao biologicos.
   - Em raios-X, procure raizes/dentes fundidos, densidade radiografica incoerente, bordas artificiais e regioes radiopacas/radiolucidas com transicao incompativel.
   - Busque texturas nao biologicas: ruido uniforme demais, gengiva artificial, esmalte/raiz com padrao plastificado ou anatomia sem separacao coerente.
   - Se houver marca grafica, seta, linha verde, texto, borrão ou recorte sobreposto, o veredito deve invalidar a imagem como MODIFICADO.

2. ANALISE MOQAM / Escaneamento por Receptividade, SEM DIAGNOSTICO:
   - Execute duas passagens independentes antes do veredito: Micro-Escala e Macro-Escala.
   - Micro-Escala: procure inconsistencias de pixel em pequenas regioes, areas de desmineralizacao aparente, bordas artificiais, textura reconstruida e sinais sutis em regioes de carie/lesao apenas como achado visual, sem diagnostico.
   - Macro-Escala: verifique continuidade biologica da mandibula, arcada, proteses, implantes, raizes e separacao entre dentes.
   - Procure dentes fundidos, raizes fundidas e transicoes anatomicas sem coerencia biologica, especialmente em imagens suspeitas de IA generativa.
   - Implantes/metais nao devem mascarar pequenas edicoes por IA; se uma estrutura brilhante dominar a imagem, ignore-a temporariamente e reavalie as regioes vizinhas.
   - Se a macro-escala parecer coerente, mas a micro-escala mostrar alteracao localizada forte, o veredito nao pode ser REAL.

3. DETECCAO DE TIPO:
   - Se for fotografia intraoral, avalie reflexos, textura de dentes/gengiva, restauracoes e coroas aparentes.
   - Se for raio-X panoramico/periapical, avalie padrao de arcada, estruturas radiopacas, implantes/proteses aparentes e coerencia visual.

FORMATO DE RESPOSTA OBRIGATORIO:
Responda SOMENTE JSON valido, sem markdown, sem pensamento interno:
{{
  "veredito": "REAL | MODIFICADO | IA_GERADA_EDITADA | INDETERMINADO",
  "confianca": "0-100%",
  "score_alteracao": 0,
  "qualidade_imagem": "boa | limitada | insuficiente",
  "artefatos_ia": ["texturas nao biologicas, dentes/raizes fundidos, densidade incoerente, se houver"],
  "integridade_primeiro": true,
  "invalidar_laudo": false,
  "analise_escala": {{
    "micro_escala": "achados pequenos de pixel/textura/borda, sem diagnostico",
    "macro_escala": "continuidade biologica ampla de arcada/mandibula/proteses/implantes/raizes",
    "conflito_escala": "se micro e macro divergem, explique a divergencia e se ela invalida REAL"
  }},
  "evidencias_visuais": ["ate 4 evidencias objetivas"],
  "disclaimer_itu": "Suporte a decisao. Responsabilidade do cirurgiao-dentista."
}}
""".strip()


def truncate_for_prompt(value: object, limit: int = 1800) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncado]"


def build_clinical_audit_prompt(
    forensic: ForensicResult,
    initial_report: str,
    initial_raw_response: str,
) -> str:
    local_forensics_data = compact_forensic_payload(forensic)
    return f"""
VOCE E O NO DE AUDITORIA CLINICA CRAG DO MODULO CODEX.

OBJETIVO:
- Reavaliar o laudo inicial cruzando achados visuais com a pericia local.
- Nao emita diagnostico odontologico. Trate carie/lesao/desmineralizacao apenas como achado visual aparente e possivel regiao de auditoria.
- Integridade vem primeiro: se achado clinico aparente conflitar com ELA, ruido, nitidez, pixel, qualidade ou MOQAM, nao permita veredito REAL.

DADOS FORENSES LOCAIS:
{local_forensics_data}

LAUDO INICIAL NORMALIZADO:
{truncate_for_prompt(initial_report, 1400)}

RESPOSTA BRUTA INICIAL DA LLM:
{truncate_for_prompt(initial_raw_response, 1600)}

TAREFA DE AUDITORIA:
1. Verifique se achados como carie/lesao aparente, dentes fundidos, densidade incoerente ou textura suspeita sao sustentados pela imagem e pelas metricas locais.
2. Se a LLM chamou algo de achado clinico, mas ELA/ruido/nitidez indicam artefato naquela regiao, trate como conflito forense.
3. Se a primeira resposta indicou MODIFICADO/IA, confirme se a conclusao tem suporte em ELA, ruido, bordas, pixels, MOQAM ou comparacao com original.
4. Se houver conflito entre micro-escala e macro-escala, priorize a integridade e revise o veredito.

FORMATO DE RESPOSTA OBRIGATORIO:
Responda SOMENTE JSON valido, sem markdown, sem pensamento interno:
{{
  "veredito": "REAL | MODIFICADO | IA_GERADA_EDITADA | INDETERMINADO",
  "veredito_revisado": "REAL | MODIFICADO | IA_GERADA_EDITADA | INDETERMINADO",
  "confianca": "0-100%",
  "score_alteracao": 0,
  "auditoria_clinica": "confirmada | revisada | conflito | inconclusiva",
  "conflitos_forenses": ["conflitos entre achado visual e ELA/ruido/nitidez/pixel/MOQAM, se houver"],
  "motivo_revisao": "explique por que manteve ou revisou o laudo inicial",
  "evidencias_visuais": ["ate 4 evidencias objetivas da auditoria"],
  "invalidar_laudo": false,
  "disclaimer_itu": "Suporte a decisao. Responsabilidade do cirurgiao-dentista."
}}
""".strip()


def run_clinical_audit(
    forensic: ForensicResult,
    initial_report: str,
    initial_raw_response: str,
    image_path: Path,
    provider: str | None = None,
) -> dict[str, Any]:
    provider = (provider or LLM_PROVIDER or "gemini").strip().lower()
    if provider not in {"gemini", "google", "gemini_flash", ""}:
        return {"audit_status": "nao_executada", "audit_evidence": []}
    if not should_run_clinical_audit(initial_report, forensic):
        return {"audit_status": "nao_executada", "audit_evidence": []}
    prompt = build_clinical_audit_prompt(forensic, initial_report, initial_raw_response)
    try:
        raw_response, model_name = call_gemini_flash(prompt, image_path, max_output_tokens=320)
        audit_report = normalize_llm_response(raw_response)
        return {
            "audit_status": "executada",
            "audit_model": model_name,
            "llm_audit_response": raw_response,
            "audit_report": audit_report,
            "audit_conflict": parsed_audit_conflict(raw_response),
            "audit_evidence": audit_evidence_from_response(raw_response, audit_report),
        }
    except Exception as exc:
        return {
            "audit_status": "falhou",
            "audit_error": str(exc),
            "audit_evidence": [f"auditoria CRAG falhou: {exc}"],
        }


def get_job_queue() -> JobQueue:
    global JOB_QUEUE
    with JOB_LOCK:
        if JOB_QUEUE is None:
            JOB_QUEUE = JobQueue(HISTORY_FILE.with_name("jobs.sqlite3"))
        return JOB_QUEUE


def analyze_image(
    image_path: Path,
    original_path: Path | None = None,
    use_llm: bool = False,
    agent_provider: str | None = None,
    model: str | None = None,
    cancelled=None,
) -> dict[str, Any]:
    provider = agent_provider or LLM_PROVIDER
    if provider == "lmstudio" and DEVELOPMENT_MODE:
        return run_integrity_pipeline(image_path, original_path,
                                      settings=replace(AI_SETTINGS, provider="lmstudio", model=model or "", development=True),
                                      cache_dir=ANALYSIS_DIR, calibration=load_calibration(), cancelled=cancelled)
    if not DEVELOPMENT_MODE or (use_llm and provider in {"gemini", "google", "gemini_flash"}):
        if provider not in {"gemini", "google", "gemini_flash"}:
            raise RuntimeError("Troca de provedor permitida apenas em desenvolvimento.")
        selected_model = model or AI_SETTINGS.model
        if selected_model not in SUPPORTED_MODELS:
            raise ValueError("Modelo nao permitido.")
        return run_integrity_pipeline(image_path, original_path, settings=replace(AI_SETTINGS, model=selected_model),
                                      cache_dir=ANALYSIS_DIR, calibration=load_calibration(), cancelled=cancelled)
    total_started = time.perf_counter()
    forensic = analyze_forensics(
        image_path,
        original_path=original_path,
        calibration=load_calibration(),
        calibration_samples=load_calibration_samples(),
    )
    if not use_llm or (forensic.skip_llm and provider != "lmstudio"):
        local_result = report_from_forensics(forensic)
        return {
            "status": "experimental",
            "verdict": local_result["verdict"],
            "report": local_result["report"],
            "duration_seconds": f"{time.perf_counter() - total_started:.2f}",
            "source": forensic.source if forensic.skip_llm else "modo_rapido_local",
            "forensic_score": forensic.score,
            "forensic_evidence": forensic.evidence,
            "forensic_quality": forensic.metrics.get("quality_status"),
            "forensic_metrics": forensic.metrics,
        }

    prompt = build_advanced_codex_prompt(forensic)

    analysis_path = prepare_analysis_image(image_path)
    if provider == "lmstudio":
        response_text = lmstudio_client.analyze(prompt, analysis_path, model or "")
        llm_source, llm_model = "experimental_lmstudio", model
    else:
        response_text, llm_source, llm_model = call_detailed_llm(prompt, analysis_path, provider=agent_provider)
    report = normalize_llm_response(response_text)
    audit_result = run_clinical_audit(forensic, report, response_text, analysis_path, provider=agent_provider)
    normalized = merge_audit_and_forensics(report, audit_result, forensic)
    return {
        "status": "experimental",
        "verdict": normalized["verdict"],
        "report": normalized["report"],
        "duration_seconds": f"{time.perf_counter() - total_started:.2f}",
        "source": llm_source,
        "model": llm_model,
        "llm_raw_response": response_text,
        "llm_initial_response": response_text,
        "llm_audit_response": audit_result.get("llm_audit_response"),
        "audit_status": audit_result.get("audit_status", "nao_executada"),
        "audit_evidence": audit_result.get("audit_evidence", []),
        "forensic_score": forensic.score,
        "forensic_evidence": forensic.evidence,
        "forensic_quality": forensic.metrics.get("quality_status"),
        "forensic_metrics": forensic.metrics,
    }


def record_analysis(result, image_path, original_path, filename, original_filename):
    entry = {
        "id": image_path.stem,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filename": filename,
        "stored_filename": image_path.name,
        "image_url": f"/uploads/{image_path.name}",
        "original_filename": original_filename if original_path is not None else None,
        "original_stored_filename": original_path.name if original_path is not None else None,
        "original_image_url": f"/uploads/{original_path.name}" if original_path is not None else None,
        "model": result.get("model", MODEL),
        "verdict": result["verdict"],
        "report": result["report"],
        "duration_seconds": result.get("duration_seconds"),
        "source": result.get("source", "llm"),
        "forensic_score": result.get("forensic_score"),
        "forensic_evidence": result.get("forensic_evidence", []),
        "forensic_quality": result.get("forensic_quality"),
        "forensic_metrics": result.get("forensic_metrics", {}),
        "llm_raw_response": result.get("llm_raw_response"),
        "llm_initial_response": result.get("llm_initial_response"),
        "llm_audit_response": result.get("llm_audit_response"),
        "audit_status": result.get("audit_status"),
        "audit_evidence": result.get("audit_evidence", []),
    }
    for key in ("schema_version", "analysis_id", "evidence_id", "status", "confidence", "structured_result", "error", "error_code", "limitations", "audit", "provider", "experimental"):
        if key in result:
            entry[key] = result[key]
    append_history(entry)
    return entry


def json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


@dataclass
class MultipartField:
    filename: str
    file: BytesIO
    value: str = ""


def parse_multipart_form(handler: BaseHTTPRequestHandler, content_type: str) -> dict[str, MultipartField]:
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length <= 0 or content_length > MAX_REQUEST_BYTES or handler.headers.get("Transfer-Encoding"):
        raise ValueError("Tamanho do formulario invalido.")
    handler.connection.settimeout(30)
    body = handler.rfile.read(content_length)
    if len(body) != content_length:
        raise ValueError("Formulario incompleto.")
    message = BytesParser(policy=email.policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
    )

    if not message.is_multipart() or message.defects:
        raise ValueError("Formulario multipart invalido.")
    form: dict[str, MultipartField] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        if name in form or len(form) >= 12:
            raise ValueError("Campos duplicados ou em excesso.")

        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        value = "" if filename else payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        form[name] = MultipartField(filename=filename, file=BytesIO(payload), value=value)
    return form


def save_uploaded_image(field: Any) -> Path:
    return save_image(field, UPLOAD_DIR)


class PeritoHandler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Closing a tab does not cancel the durable analysis job.
            self.close_connection = True

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        super().end_headers()

    def valid_origin(self):
        expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in expected:
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in {"http://" + host for host in expected}

    def do_GET(self) -> None:
        if not self.valid_origin():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        parsed_url = urlparse(self.path)
        request_path = parsed_url.path

        if re.fullmatch(r"/jobs/[a-f0-9]{32}", request_path):
            job = get_job_queue().get(request_path.rsplit("/", 1)[1])
            json_response(self, HTTPStatus.OK if job else HTTPStatus.NOT_FOUND, job or {"error": "Analise nao encontrada."})
            return

        if request_path in {"/static/app.css", "/static/app.js"}:
            path = STATIC_DIR / request_path.rsplit("/", 1)[1]
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8" if path.suffix == ".css" else "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if request_path == "/history":
            query = parse_qs(parsed_url.query)
            tab = (query.get("tab", ["all"])[0] or "all").strip().lower()
            try:
                page = int(query.get("page", ["1"])[0])
            except (TypeError, ValueError):
                page = 1
            try:
                page_size = int(query.get("page_size", [str(HISTORY_PAGE_SIZE)])[0])
            except (TypeError, ValueError):
                page_size = HISTORY_PAGE_SIZE
            json_response(self, HTTPStatus.OK, paginated_history(tab, page, page_size, query.get("model", [""])[0]))
            return

        if request_path == "/metrics":
            json_response(
                self,
                HTTPStatus.OK,
                {"estimated_seconds": round(estimated_analysis_seconds(), 2)},
            )
            return

        if request_path == "/agents":
            agents = available_agents()
            preferred = LLM_PROVIDER if LLM_PROVIDER in {"gemini", "google", "gemini_flash", "ollama"} else "gemini"
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "default_provider": "gemini" if preferred in {"google", "gemini_flash"} else preferred,
                    "agents": agents,
                    **model_catalog(),
                    "default_model": GEMINI_MODEL,
                    "development_mode": DEVELOPMENT_MODE,
                },
            )
            return

        if request_path.startswith("/analysis/"):
            analysis_id = request_path.removeprefix("/analysis/")
            exporting = analysis_id.endswith("/export")
            if exporting:
                analysis_id = analysis_id.removesuffix("/export")
            if not re.fullmatch(r"[a-f0-9]{32}", analysis_id):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            saved_result = ANALYSIS_DIR / analysis_id / "result.json"
            if not saved_result.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            payload = json.loads(saved_result.read_text(encoding="utf-8"))
            if exporting:
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Disposition", f'attachment; filename="analysis-{analysis_id}.json"')
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            json_response(self, HTTPStatus.OK, payload)
            return

        if request_path.startswith("/uploads/"):
            filename = Path(unquote(request_path.removeprefix("/uploads/"))).name
            image_path = UPLOAD_DIR / filename
            if not image_path.exists() or image_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                self.send_error(HTTPStatus.NOT_FOUND, "Imagem nao encontrada")
                return

            content_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
            }.get(image_path.suffix.lower(), "application/octet-stream")
            body = image_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if request_path not in {"/", "/index.html"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada")
            return

        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path == '/calibrate':
            try:
                with file_lock(RUNTIME_DIR / '.dataset.lock'):
                    self.handle_post()
            except ResourceBusy as exc:
                json_response(self, HTTPStatus.CONFLICT, {'error': str(exc)})
            return
        self.handle_post()

    def handle_post(self) -> None:
        if not self.valid_origin():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if re.fullmatch(r"/jobs/[a-f0-9]{32}/cancel", self.path):
            job = get_job_queue().cancel(self.path.split("/")[2])
            json_response(self, HTTPStatus.OK if job else HTTPStatus.NOT_FOUND, job or {"error": "Analise nao encontrada."})
            return
        if self.path not in {"/analyze", "/calibrate"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado")
            return

        if self.path == "/calibrate" and not DEVELOPMENT_MODE:
            json_response(self, HTTPStatus.FORBIDDEN, {"error": "Calibracao permitida apenas em desenvolvimento."})
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Envie um formulario multipart com o campo image."})
            return

        try:
            form = parse_multipart_form(self, content_type)
        except (ValueError, TimeoutError, OSError):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Formulario multipart invalido."})
            return
        field = form["image"] if "image" in form else None
        if field is None or not getattr(field, "filename", ""):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Nenhuma imagem foi enviada."})
            return

        use_llm = "use_llm" in form and str(getattr(form["use_llm"], "value", "")).lower() in {"1", "true", "sim", "on"}
        agent_provider = str(getattr(form.get("agent_provider"), "value", "") or "").strip().lower() or None
        model = str(getattr(form.get("model"), "value", "") or "").strip() or None
        if self.path == '/analyze':
            if agent_provider != "lmstudio" and model is not None and model not in SUPPORTED_MODELS:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Modelo nao permitido."})
                return
            if not DEVELOPMENT_MODE and agent_provider not in {None, "gemini"}:
                json_response(self, HTTPStatus.FORBIDDEN, {"error": "Producao exige o provedor Gemini."})
                return
        else:
            label = canonical_integrity_label(str(getattr(form.get('label'), 'value', 'MODIFICADO')).upper())
            if label not in {"REAL", "MODIFICADO", "IA_GERADA_EDITADA"}:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Rotulo invalido. Use REAL, MODIFICADO ou IA_GERADA_EDITADA."})
                return

        try:
            image_path = save_uploaded_image(field)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        original_field = form["original_image"] if "original_image" in form else None
        original_path: Path | None = None
        if original_field is not None and getattr(original_field, "filename", ""):
            try:
                original_path = save_uploaded_image(original_field)
            except ValueError as exc:
                image_path.unlink(missing_ok=True)
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"Imagem original: {exc}"})
                return

        if self.path == "/calibrate":
            try:
                protected = held_out_hashes(RUNTIME_DIR / "datasets" / "manifest.json")
                if file_sha256(image_path) in protected or (original_path and file_sha256(original_path) in protected):
                    raise ValueError("Imagem reservada para teste; nao pode entrar na calibracao.")
            except ValueError as exc:
                image_path.unlink(missing_ok=True)
                if original_path:
                    original_path.unlink(missing_ok=True)
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            result = calibrated_feedback_result(label)
            result["status"] = "experimental"
            calibration = load_calibration()
            calibration_entry = dict(result["calibration_entry"])
            forensic_metrics = local_metrics(image_path)
            calibration_entry["features"] = feature_profile_from_metrics(forensic_metrics)
            calibration_entry["quality_status"] = forensic_metrics.get("quality_status")
            calibration_entry["stored_filename"] = image_path.name
            calibration_entry["learned_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result["forensic_metrics"] = forensic_metrics
            result["forensic_quality"] = forensic_metrics.get("quality_status")
            if original_path is not None:
                comparison = compare_with_original(image_path, original_path)
                comparison_features = comparison_feature_profile(comparison)
                forensic_metrics["comparison"] = comparison
                calibration_entry["original_sha256"] = file_sha256(original_path)
                calibration_entry["original_stored_filename"] = original_path.name
                calibration_entry["comparison"] = comparison
                calibration_entry["comparison_features"] = comparison_features
                calibration_entry["evidence"] = (
                    f"{calibration_entry['evidence']}; padrao comparativo salvo contra imagem original"
                )
                if label in {"MODIFICADO", "IA_GERADA_EDITADA"}:
                    if label == "IA_GERADA_EDITADA":
                        calibration_entry["justification"] = (
                            "A imagem foi marcada pelo usuario como edicao ou geracao por IA em comparacao com a original enviada."
                        )
                    else:
                        calibration_entry["justification"] = (
                            "A imagem foi marcada pelo usuario como modificada em comparacao com a original enviada."
                    )
                    original_entry = calibration_entry_for_label("REAL")
                    original_metrics = local_metrics(original_path)
                    original_entry["features"] = feature_profile_from_metrics(original_metrics)
                    original_entry["quality_status"] = original_metrics.get("quality_status")
                    original_entry["stored_filename"] = original_path.name
                    original_entry["learned_at"] = calibration_entry["learned_at"]
                    original_entry["paired_modified_sha256"] = file_sha256(image_path)
                    original_entry["evidence"] = "imagem original associada a par comparativo marcado pelo usuario"
                    original_entry["justification"] = (
                        "A imagem foi marcada como original de referencia para aprendizado local comparativo."
                    )
                    calibration[file_sha256(original_path)] = original_entry
                result["source"] = "feedback_usuario_comparacao"
                result["forensic_evidence"] = [calibration_entry["evidence"]]
                result["forensic_metrics"] = forensic_metrics
                result["forensic_quality"] = forensic_metrics.get("quality_status")
                refreshed_report = "\n".join(
                    [
                        f"VEREDITO: {calibration_entry['label']}",
                        f"CONFIANCA: {calibration_entry['confidence']}",
                        f"JUSTIFICATIVA: {calibration_entry['justification']}",
                        f"TIPO: {calibration_entry['type']}",
                        f"SCORE_ALTERACAO: {calibration_entry['score']}",
                        f"EVIDENCIAS: {calibration_entry['evidence']}",
                    ]
                )
                normalized = normalize_report(refreshed_report)
                result["verdict"] = normalized["verdict"]
                result["report"] = normalized["report"]
            calibration[file_sha256(image_path)] = calibration_entry
            save_calibration(calibration)

            entry = {
                "id": image_path.stem,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filename": Path(field.filename).name,
                "stored_filename": image_path.name,
                "image_url": f"/uploads/{image_path.name}",
                "original_filename": Path(original_field.filename).name if original_path is not None else None,
                "original_stored_filename": original_path.name if original_path is not None else None,
                "original_image_url": f"/uploads/{original_path.name}" if original_path is not None else None,
                "model": "calibracao_local",
                "status": "experimental",
                "verdict": result["verdict"],
                "report": result["report"],
                "duration_seconds": result["duration_seconds"],
                "source": result["source"],
                "forensic_score": result["forensic_score"],
                "forensic_evidence": result["forensic_evidence"],
                "forensic_quality": result.get("forensic_quality"),
                "forensic_metrics": result.get("forensic_metrics", {}),
            }
            append_history(entry)
            payload = {key: value for key, value in result.items() if key != "calibration_entry"}
            json_response(self, HTTPStatus.OK, {**payload, "history_item": entry})
            return

        # Both legacy synchronous callers and the UI share the same bounded worker.
        if self.path == "/analyze":
            filename = Path(field.filename).name
            original_filename = Path(original_field.filename).name if original_path else None
            def operation(cancelled):
                result = analyze_image(image_path, original_path, use_llm=use_llm,
                                       agent_provider=agent_provider, model=model, cancelled=cancelled)
                if not cancelled():
                    entry = record_analysis(result, image_path, original_path, filename, original_filename)
                    result["history_item"] = entry
                return result
            try:
                identifier = get_job_queue().submit(operation)
            except QueueFull as exc:
                image_path.unlink(missing_ok=True)
                if original_path:
                    original_path.unlink(missing_ok=True)
                json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
                return
            if self.headers.get("Prefer") == "respond-async":
                json_response(self, HTTPStatus.ACCEPTED, {"job_id": identifier, "state": "aguardando"})
                return
            while True:
                job = get_job_queue().get(identifier)
                if job["state"] in {"concluida", "falhou", "cancelada"}:
                    payload = job.get("result", {"status": "nao_concluida", "verdict": None, "error": job.get("error", "Analise cancelada.")})
                    status = HTTPStatus.OK if job["state"] == "concluida" else HTTPStatus.SERVICE_UNAVAILABLE
                    json_response(self, status, payload)
                    break
                time.sleep(0.1)
            return

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def serve() -> int:
    configure_stdio()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    if HISTORY_FILE.exists():
        save_history(load_history())
    server = ThreadingHTTPServer(("127.0.0.1", PORT), PeritoHandler)
    print(f"Pagina web: http://127.0.0.1:{PORT}")
    print(f"LLM detalhada: {LLM_PROVIDER} | Gemini: {GEMINI_MODEL} | Ollama: {OLLAMA_HOST} / {MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Servidor encerrado.")
    finally:
        if JOB_QUEUE is not None:
            JOB_QUEUE.close()
        server.server_close()
    return 0


def main() -> int:
    with file_lock(RUNTIME_DIR / '.service.lock'):
        return serve()


if __name__ == "__main__":
    raise SystemExit(main())
