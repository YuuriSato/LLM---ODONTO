import json
from pathlib import Path
import time
import uuid

from app.ai.audit import audit_analysis
from app.ai.config import AISettings, PROMPT_VERSION, SCHEMA_VERSION, get_settings
from app.ai.evidence import collect_evidence
from app.ai.gemini_client import GeminiClient, ProviderError
from app.ai.gemini_integrity_analyzer import AnalysisValidationError, GeminiIntegrityAnalyzer


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def run_integrity_pipeline(image: Path, reference: Path | None = None, *, settings: AISettings | None = None,
                           cache_dir: Path | None = None, calibration: dict | None = None,
                           analyzer: GeminiIntegrityAnalyzer | None = None, detector=None) -> dict:
    started = time.perf_counter()
    settings = settings or get_settings()
    analysis_id = uuid.uuid4().hex
    folder = (cache_dir or Path(__file__).resolve().parents[2] / "runtime" / "analysis_cache") / analysis_id
    folder.mkdir(parents=True, exist_ok=False)
    evidence = collect_evidence(image, analysis_id, reference, calibration, detector)
    save_json(folder / "local_evidence.json", evidence.model_dump(mode="json"))
    analyzer = analyzer or GeminiIntegrityAnalyzer(GeminiClient(settings))
    result = {
        "schema_version": SCHEMA_VERSION, "analysis_id": analysis_id, "evidence_id": analysis_id,
        "status": "nao_concluida", "verdict": None, "confidence": None,
        "source": "gemini_integrity_pipeline", "model": settings.model,
        "prompt_version": PROMPT_VERSION, "initial_analysis": None, "reviewed_analysis": None,
        "structured_result": None, "audit": None, "audit_status": "nao_executada", "audit_evidence": [],
        "forensic_score": None, "forensic_evidence": evidence.observations,
        "forensic_quality": evidence.quality,
        "forensic_metrics": {r.id: r.values for r in evidence.records},
        "limitations": evidence.limitations, "local_evidence": evidence.model_dump(mode="json"),
    }
    try:
        settings.validate_production()
        initial = analyzer.analyze_integrity(image, evidence, reference)
        result["initial_analysis"] = initial.model_dump(mode="json")
        audit = audit_analysis(initial, evidence)
        result["initial_audit"] = audit
        result["audit"] = audit
        result["audit_status"] = "executada"
        final = initial
        if audit["requires_review"]:
            result["review_status"] = "solicitada"
            final = analyzer.review(image, evidence, initial, audit, reference)
            result["reviewed_analysis"] = final.model_dump(mode="json")
            result["review_status"] = "executada"
            audit = audit_analysis(final, evidence, reviewed=True)
        result.update(status="concluida", verdict=audit["verdict"], confidence=audit["confidence"],
                      audit=audit, audit_evidence=audit["reasons"], audit_status="executada")
        justification = final.justificativa
        if audit["reasons"]:
            justification = "Conclusao indeterminada: " + " ".join(audit["reasons"])
        result["structured_result"] = {
            "veredito": audit["verdict"], "confidence": audit["confidence"],
            "confidence_kind": audit["confidence_kind"], "modalidade": final.modalidade,
            "justificativa": justification, "limitacoes": list(dict.fromkeys(evidence.limitations + final.limitacoes)),
        }
        result["limitations"] = result["structured_result"]["limitacoes"]
        result["report"] = f"VEREDITO: {audit['verdict']}\nJUSTIFICATIVA: {justification}\nEVIDENCIAS: " + "; ".join(evidence.observations)
    except (ProviderError, AnalysisValidationError, ValueError) as exc:
        result["error_code"] = getattr(exc, "code", "invalid_configuration")
        result["error"] = str(exc)
        result["report"] = "Analise nao concluida: " + str(exc)
        if result.get("review_status") == "solicitada":
            result["review_status"] = "falhou"
    result["duration_seconds"] = f"{time.perf_counter() - started:.2f}"
    result["provider_calls"] = analyzer.calls
    save_json(folder / "result.json", result)
    return result
