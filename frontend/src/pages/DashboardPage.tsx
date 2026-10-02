import { AlertTriangle, Ban, CheckCircle2, Files, WandSparkles, XCircle } from 'lucide-react';
import { AgentList } from '../components/AgentList';
import { PageHeader } from '../components/PageHeader';
import { useHistory } from '../hooks/useHistory';
import type { Agent } from '../types';

export function DashboardPage({ agents, agentsLoading }: { agents: Agent[]; agentsLoading: boolean }) {
  const { data, loading, error, refresh } = useHistory(true);
  const counts = data.pagination.counts || {};
  const cards = [
    { id: 'dashTotal', label: 'Total de análises', value: data.pagination.total_all, detail: 'Registros armazenados localmente', icon: Files },
    { id: 'dashModified', label: 'Alterações ou IA', value: counts.modified || 0, detail: 'Resultados com sinais de alteração', icon: WandSparkles },
    { id: 'dashReal', label: 'Sem alteração detectada', value: counts.real || 0, detail: 'Resultados classificados como reais', icon: CheckCircle2 },
    { id: 'dashInconclusive', label: 'Inconclusivas', value: counts.inconclusive || 0, detail: 'Evidências não distinguem as hipóteses', icon: AlertTriangle },
    { id: 'dashImpossible', label: 'Impossíveis de avaliar', value: counts.impossible || 0, detail: 'Qualidade impediu uma análise útil', icon: Ban },
    { id: 'dashFailed', label: 'Não concluídas', value: counts.failed || 0, detail: 'Falhas técnicas que podem ser repetidas', icon: XCircle },
  ];
  return (
    <div className="page" data-page-panel="dashboard">
      <PageHeader eyebrow="Visão geral" title="Painel" description="Resumo das análises e da disponibilidade dos modelos." />
      {error && <div className="message error" role="alert">{error} <button type="button" onClick={() => void refresh()}>Tentar novamente</button></div>}
      <section className="stats-grid" aria-label="Resumo das análises">
        {cards.map((card) => (
          <article className="stat-card" key={card.id} aria-busy={loading}>
            <div><span>{card.label}</span><card.icon aria-hidden="true" size={20} /></div>
            <strong id={card.id}>{loading ? '—' : card.value}</strong>
            <p>{card.detail}</p>
          </article>
        ))}
      </section>
      <section className="content-section">
        <div className="section-heading"><div><span className="section-label">Disponibilidade</span><h2>Modelos detectados</h2></div></div>
        <AgentList agents={agents} loading={agentsLoading} />
      </section>
    </div>
  );
}
