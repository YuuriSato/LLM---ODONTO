import { AlertTriangle, CheckCircle2, FlaskConical, Info, ShieldCheck, XCircle } from 'lucide-react';
import type { AnalysisResult } from '../types';

const verdictLabels: Record<string, string> = {
  REAL: 'Imagem sem alteração detectada',
  IA_GERADA: 'Imagem gerada por inteligência artificial',
  IA_EDITADA: 'Imagem editada por inteligência artificial',
  EDICAO_TRADICIONAL: 'Imagem com edição tradicional',
  MODIFICADO: 'Imagem modificada',
  IA_GERADA_EDITADA: 'Imagem gerada ou editada por IA',
  INDETERMINADO: 'Análise inconclusiva',
};

function reportValue(report: string | undefined, label: string) {
  const match = String(report || '').match(new RegExp(`^${label}:\\s*(.+)$`, 'im'));
  return match?.[1]?.trim() || '';
}

function textValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>;
    return String(item.descricao || item.texto || item.alegacao || item.evidencia || JSON.stringify(value));
  }
  return String(value ?? '');
}

function compactEvidence(result: AnalysisResult, full: boolean) {
  const source = Array.isArray(result.forensic_evidence)
    ? result.forensic_evidence.map(textValue).filter(Boolean).join('; ')
    : String(result.forensic_evidence || reportValue(result.report, 'EVIDENCIAS'));
  if (full || source.length <= 360) return source;
  return `${source.slice(0, 357).trim()}...`;
}

function resultPresentation(result: AnalysisResult) {
  const failed = result.status === 'nao_concluida';
  const experimental = result.status === 'experimental' || result.experimental;
  const inconclusive = result.verdict === 'INDETERMINADO';
  if (failed) return { label: 'Análise não concluída', tone: 'danger', Icon: XCircle };
  if (experimental) return { label: `Teste experimental: ${verdictLabels[String(result.verdict)] || result.verdict || 'sem conclusão'}`, tone: 'warning', Icon: FlaskConical };
  if (inconclusive) return { label: 'Análise inconclusiva', tone: 'warning', Icon: AlertTriangle };
  if (result.verdict === 'REAL') return { label: verdictLabels.REAL, tone: 'success', Icon: CheckCircle2 };
  return { label: verdictLabels[String(result.verdict)] || String(result.verdict || 'Resultado disponível'), tone: 'danger', Icon: AlertTriangle };
}

export function ResultPanel({ result, showFullEvidence }: { result: AnalysisResult; showFullEvidence: boolean }) {
  const presentation = resultPresentation(result);
  const reasons = [
    result.structured_result?.justificativa,
    ...(result.structured_result?.evidencias_favoraveis || []).map(textValue),
    compactEvidence(result, showFullEvidence),
  ].filter(Boolean);
  const limitations = (result.structured_result?.limitacoes || []).map(textValue).filter(Boolean);
  const quality = String(result.forensic_quality || result.forensic_metrics?.quality_status || 'Não informada');
  const audit = result.audit_status && result.audit_status !== 'nao_executada'
    ? result.audit_status.replaceAll('_', ' ')
    : 'Não informada';

  return (
    <section id="result" className={`result-panel ${presentation.tone}`} aria-live="polite">
      <div className="result-heading">
        <span className={`result-icon ${presentation.tone}`}><presentation.Icon aria-hidden="true" size={22} /></span>
        <div>
          <span className="section-label">Conclusão</span>
          <h2 id="verdict">{presentation.label}</h2>
          {result.status === 'nao_concluida' && <p>{result.error || result.report || 'O servidor não conseguiu concluir esta execução.'}</p>}
        </div>
      </div>

      {result.status !== 'nao_concluida' && (
        <>
          <div className="result-section">
            <div className="section-title"><ShieldCheck aria-hidden="true" size={18} /><h3>Motivos</h3></div>
            {reasons.length ? <ul>{reasons.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}</ul> : <p>Nenhum motivo resumido foi informado.</p>}
          </div>
          <div className="result-section">
            <div className="section-title"><Info aria-hidden="true" size={18} /><h3>Limitações</h3></div>
            {limitations.length ? <ul>{limitations.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>Nenhuma limitação adicional foi informada.</p>}
          </div>
        </>
      )}

      <details className="technical-details">
        <summary>Detalhes técnicos</summary>
        <div id="forensics" className="technical-grid">
          {result.schema_version !== '2.0' && <div><span>Score local</span><strong id="forensicScore">{result.forensic_score != null ? `${result.forensic_score}%` : 'Não informado'}</strong></div>}
          <div><span>Fonte</span><strong id="forensicSource">{result.source || 'Não informada'}</strong></div>
          <div><span>Qualidade da imagem</span><strong id="forensicQuality">{quality}</strong></div>
          <div><span>Verificação das evidências</span><strong id="forensicAudit">{audit}</strong></div>
          <div className="technical-wide"><span>Evidências locais</span><strong id="forensicEvidence">{compactEvidence(result, showFullEvidence) || 'Não informadas'}</strong></div>
          <div className="technical-wide"><span>Modelo</span><strong>{result.model || 'Não informado'}</strong></div>
          {showFullEvidence && <pre id="report">{JSON.stringify(result, null, 2)}</pre>}
        </div>
      </details>
    </section>
  );
}
