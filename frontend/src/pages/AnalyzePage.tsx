import { RotateCcw, Send, Square } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { AnalysisStatus } from '../components/AnalysisStatus';
import { FilePicker } from '../components/FilePicker';
import { ModelSelector } from '../components/ModelSelector';
import { PageHeader } from '../components/PageHeader';
import { ResultPanel } from '../components/ResultPanel';
import { useAnalysisJob } from '../hooks/useAnalysisJob';
import { useObjectUrl } from '../hooks/useObjectUrl';
import type { SelectedModel } from '../types';

export function AnalyzePage({ models, selected, selectedValue, catalogLoading, catalogError, setSelectedValue, refreshModels, showFullEvidence }: {
  models: SelectedModel[];
  selected: SelectedModel | null;
  selectedValue: string;
  catalogLoading: boolean;
  catalogError: string;
  setSelectedValue: (value: string) => void;
  refreshModels: () => Promise<void>;
  showFullEvidence: boolean;
}) {
  const [image, setImage] = useState<File | null>(null);
  const [original, setOriginal] = useState<File | null>(null);
  const [estimate, setEstimate] = useState<number | null>(null);
  const imageUrl = useObjectUrl(image);
  const originalUrl = useObjectUrl(original);
  const onComplete = useCallback(() => undefined, []);
  const analysis = useAnalysisJob(onComplete);

  useEffect(() => { api.getEstimate().then(setEstimate).catch(() => setEstimate(null)); }, []);
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (image && selected?.available) void analysis.submit(image, original, selectedValue);
  };
  const statusText = analysis.connectionLost
    ? 'A conexão foi interrompida. A análise continua no servidor e pode ser retomada sem reenviar a imagem.'
    : analysis.error;

  return (
    <div className="page" data-page-panel="analyze">
      <PageHeader eyebrow="Integridade visual" title="Analisar imagem" description="Análise de imagens odontológicas, sem diagnóstico clínico." />
      <div className="analysis-grid">
        <form id="form" className="panel upload-panel" onSubmit={submit}>
          <ModelSelector
            models={models}
            value={selectedValue}
            loading={catalogLoading}
            error={catalogError}
            onChange={setSelectedValue}
            onRefresh={refreshModels}
            disabled={analysis.busy}
          />
          <div className="upload-fields">
            <FilePicker id="image" label="Imagem para análise" hint="PNG, JPEG, WebP ou BMP, até o limite configurado no servidor." file={image} onChange={setImage} disabled={analysis.busy} required removeLabel="Remover imagem para análise" />
            <FilePicker id="originalImage" label="Imagem original opcional" hint="Adicione uma referência para comparação lado a lado." file={original} onChange={setOriginal} disabled={analysis.busy} removeLabel="Remover imagem original" />
          </div>
          {(imageUrl || originalUrl) && (
            <div className="preview-grid" aria-label="Prévia das imagens">
              {imageUrl && <figure><img id="preview" className="preview" src={imageUrl} alt="Prévia da imagem para análise" /><figcaption>Imagem para análise</figcaption></figure>}
              {originalUrl && <figure><img id="originalPreview" className="preview" src={originalUrl} alt="Prévia da imagem original" /><figcaption>Imagem original</figcaption></figure>}
            </div>
          )}
          <div className="form-actions">
            <button id="submit" className="primary-button" type="submit" disabled={analysis.busy || !image || !selected?.available}>
              <Send aria-hidden="true" size={18} />Analisar imagem
            </button>
            {analysis.jobId && <button id="cancelAnalysis" className="secondary-button danger-button" type="button" onClick={() => void analysis.cancel()}><Square aria-hidden="true" size={17} />Cancelar</button>}
            {analysis.connectionLost && <button id="resumeAnalysis" className="secondary-button" type="button" onClick={() => void analysis.resume()}><RotateCcw aria-hidden="true" size={17} />Retomar acompanhamento</button>}
          </div>
          <AnalysisStatus state={analysis.state} estimate={estimate} />
          <div id="status" className={`message ${statusText ? 'error' : ''}`} role="status">
            {statusText || (analysis.state === 'concluida' ? 'Análise concluída.' : '')}
          </div>
        </form>
        {analysis.result ? <ResultPanel result={analysis.result} showFullEvidence={showFullEvidence} onRetry={() => void analysis.retry()} retrying={analysis.busy} /> : (
          <aside className="result-placeholder">
            <div><span>01</span><strong>Envie a imagem</strong><p>O arquivo é verificado e as evidências locais são preservadas.</p></div>
            <div><span>02</span><strong>Aguarde a análise</strong><p>As etapas exibidas refletem o estado informado pelo servidor.</p></div>
            <div><span>03</span><strong>Revise o resultado</strong><p>Conclusão, motivos, limitações e detalhes técnicos ficam separados.</p></div>
          </aside>
        )}
      </div>
    </div>
  );
}
