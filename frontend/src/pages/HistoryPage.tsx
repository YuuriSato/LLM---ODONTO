import { Download, Eye, ImageOff, RefreshCw, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { useHistory } from '../hooks/useHistory';
import type { HistoryItem } from '../types';

const tabs = [
  ['all', 'Todas'], ['modified', 'Alteradas / IA'], ['real', 'Reais'],
  ['inconclusive', 'Inconclusivas'], ['impossible', 'Impossíveis'], ['failed', 'Falhas'], ['calibration', 'Calibração'],
] as const;

const labels: Record<string, string> = {
  REAL: 'Sem alteração detectada', IA_GERADA: 'Gerada por IA', IA_EDITADA: 'Editada por IA',
  EDICAO_TRADICIONAL: 'Edição tradicional', MODIFICADO: 'Modificada',
  IA_GERADA_EDITADA: 'Gerada ou editada por IA', INDETERMINADO: 'Inconclusiva',
};

function historyTone(item: HistoryItem) {
  if (item.status === 'nao_concluida') return 'danger';
  if (item.status === 'experimental' || item.experimental) return 'warning';
  if (item.verdict === 'REAL') return 'success';
  if (item.verdict === 'INDETERMINADO') return 'warning';
  return 'danger';
}

function itemTitle(item: HistoryItem) {
  if (item.status === 'nao_concluida') return 'Falha de execução';
  if (item.conclusion_type === 'impossivel_avaliar') return 'Impossível de avaliar';
  const verdict = labels[String(item.verdict)] || item.verdict || 'Sem conclusão';
  return item.status === 'experimental' || item.experimental ? `Teste experimental: ${verdict}` : verdict;
}

export function HistoryPage() {
  const history = useHistory(true);
  const [comparison, setComparison] = useState<HistoryItem | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (comparison) dialog.current?.showModal();
    else dialog.current?.close();
  }, [comparison]);
  const pagination = history.data.pagination;

  return (
    <div className="page" data-page-panel="history">
      <PageHeader eyebrow="Registros locais" title="Histórico" description="Consulte análises, compare imagens e exporte as evidências completas." actions={<span id="historyCount" className="record-count">{pagination.total_all} {pagination.total_all === 1 ? 'registro' : 'registros'}</span>} />
      <section className="history-controls" aria-label="Filtros do histórico">
        <div id="historyTabs" className="segmented-control" role="tablist" aria-label="Tipo de resultado">
          {tabs.map(([value, label]) => (
            <button key={value} type="button" role="tab" data-tab={value} aria-selected={history.tab === value} className={history.tab === value ? 'active' : ''} onClick={() => history.changeTab(value)}>
              {label}<span className="history-tab-count">{pagination.counts?.[value] || 0}</span>
            </button>
          ))}
        </div>
        <div className="compact-field">
          <label htmlFor="historyModel">Modelo</label>
          <select id="historyModel" value={history.model} onChange={(event) => history.changeModel(event.target.value)}>
            <option value="">Todos os modelos</option>
            {history.data.models.map((model) => <option value={model} key={model}>{model}</option>)}
          </select>
        </div>
      </section>

      {history.error && <div className="message error" role="alert">{history.error}<button type="button" onClick={() => void history.refresh()}><RefreshCw aria-hidden="true" size={16} />Tentar novamente</button></div>}
      {history.loading ? <div className="loading-state" aria-live="polite">Carregando histórico...</div> : history.data.history.length ? (
        <div id="historyList" className="history-list">
          {history.data.history.map((item, index) => (
            <article className="history-item" key={item.analysis_id || item.id || index}>
              <div className="history-thumbnail">{item.image_url ? <img src={item.image_url} alt="Miniatura da imagem analisada" /> : <ImageOff aria-label="Imagem indisponível" size={28} />}</div>
              <div className="history-content">
                <div className="history-meta"><span>{item.created_at || 'Data não informada'}</span><span>{item.model || 'Modelo não informado'}</span></div>
                <h2 className={`history-verdict ${historyTone(item)}`}>{itemTitle(item)}</h2>
                <p className="history-report">{item.structured_result?.justificativa || item.error || item.report || 'Sem resumo disponível.'}</p>
                <div className="history-actions">
                  {item.image_url && item.original_image_url && <button type="button" className="text-button" onClick={() => setComparison(item)}><Eye aria-hidden="true" size={17} />Comparar</button>}
                  {item.analysis_id && <a href={`/analysis/${item.analysis_id}/export`} download><Download aria-hidden="true" size={17} />Exportar evidências</a>}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <div id="historyList" className="empty-state"><ImageOff aria-hidden="true" size={28} /><strong>Nenhum registro encontrado</strong><p>Ajuste os filtros ou faça uma nova análise.</p></div>}

      <div className="history-pager" aria-label="Paginação do histórico">
        <span id="historyRange">{pagination.total ? `${pagination.start}-${pagination.end} de ${pagination.total}` : '0 registros nesta seleção'}</span>
        <div>
          <button id="historyPrev" className="icon-button" type="button" aria-label="Página anterior" disabled={pagination.page <= 1} onClick={() => history.setPage(pagination.page - 1)}>‹</button>
          <span id="historyPageLabel">Página {pagination.page} de {pagination.total_pages}</span>
          <button id="historyNext" className="icon-button" type="button" aria-label="Próxima página" disabled={pagination.page >= pagination.total_pages} onClick={() => history.setPage(pagination.page + 1)}>›</button>
        </div>
      </div>

      <dialog id="comparisonDialog" ref={dialog} onCancel={() => setComparison(null)}>
        <div className="dialog-heading"><div><span className="section-label">Comparação visual</span><h2>Original e imagem analisada</h2></div><button id="closeComparison" className="icon-button" type="button" aria-label="Fechar comparação" onClick={() => setComparison(null)}><X aria-hidden="true" size={20} /></button></div>
        <div className="comparison-grid">
          <figure><img id="compareReference" src={comparison?.original_image_url} alt="Imagem original de referência" /><figcaption>Imagem original</figcaption></figure>
          <figure><img id="compareAnalyzed" src={comparison?.image_url} alt="Imagem analisada" /><figcaption>Imagem analisada</figcaption></figure>
        </div>
      </dialog>
    </div>
  );
}
