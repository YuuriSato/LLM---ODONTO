from app.ai.schemas import IntegrityAnalysis, LocalEvidence, Verdict, validate_references


LOCAL_FAMILIES = {"compressao", "textura", "sobreposicao", "comparacao"}


def audit_analysis(analysis: IntegrityAnalysis, evidence: LocalEvidence, *, reviewed: bool = False) -> dict:
    validate_references(analysis, evidence)
    records = {record.id: record for record in evidence.records}
    anomalous = {r.family for r in evidence.records if r.status == "disponivel" and r.signal == "anomalia" and r.family in LOCAL_FAMILIES}
    reasons = []
    if evidence.quality in {"insuficiente", "desconhecida"}:
        reasons.append("Qualidade insuficiente ou desconhecida para conclusao confiavel.")
    if any(records[key].status != "disponivel" for key in ("ela", "ruido", "nitidez")):
        reasons.append("Extracao de evidencias essenciais incompleta.")

    supported = set()
    expected_signal = "sem_anomalia" if analysis.veredito == Verdict.REAL else "anomalia"
    for claim in analysis.evidencias_favoraveis:
        for ref in claim.referencias:
            record = records[ref.evidence_id]
            if record.family in LOCAL_FAMILIES and record.signal == expected_signal:
                supported.add(record.family)
    visual_support = any(claim.fonte == "visual" for claim in analysis.evidencias_favoraveis)
    if analysis.veredito != Verdict.INDETERMINADO:
        if len(supported) < 2 or not visual_support:
            reasons.append("Suporte visual e computacional insuficiente em familias distintas de evidencias.")
        if analysis.evidencias_contrarias:
            reasons.append("Ha evidencias contrarias a conclusao proposta.")
        if analysis.veredito == Verdict.REAL and anomalous:
            reasons.append("Veredito REAL diverge das inconsistencias forenses locais.")

    detector = records["detector_ia"]
    detector_high = detector.status == "disponivel" and detector.signal == "anomalia"
    detector_low = detector.status == "disponivel" and detector.signal == "sem_anomalia"
    ai_verdict = analysis.veredito in {Verdict.IA_EDITADA, Verdict.IA_GERADA}
    if ai_verdict and detector_low:
        reasons.append("Hipotese de IA diverge do detector externo.")
    if analysis.veredito == Verdict.REAL and detector_high:
        reasons.append("Veredito REAL diverge do detector externo.")
    if reviewed and analysis.requer_auditoria:
        reasons.append("A revisao ainda solicita auditoria adicional.")

    invalidated = bool(reasons)
    verdict = Verdict.INDETERMINADO if invalidated else analysis.veredito
    return {
        "status": "conflito" if invalidated else "validada",
        "reasons": reasons,
        "requires_review": not reviewed and (invalidated or analysis.requer_auditoria),
        "suspeita_ia": ai_verdict or (len(anomalous) >= 2 and detector_high),
        "support_families": sorted(supported),
        "anomalous_families": sorted(anomalous),
        "verdict": verdict.value,
        "confidence": None if invalidated else analysis.confidence,
        "confidence_kind": "declarada_pelo_modelo_nao_calibrada",
    }
