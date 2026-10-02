import { AgentList } from '../components/AgentList';
import { PageHeader } from '../components/PageHeader';
import type { Agent, AgentCatalog } from '../types';

export function SettingsPage({ showFullEvidence, setShowFullEvidence, agents, catalog, loading, error }: {
  showFullEvidence: boolean;
  setShowFullEvidence: (value: boolean) => void;
  agents: Agent[];
  catalog: AgentCatalog | null;
  loading: boolean;
  error: string;
}) {
  return (
    <div className="page" data-page-panel="settings">
      <PageHeader eyebrow="Preferências locais" title="Configurações" description="Controle a apresentação dos resultados e consulte os modelos detectados." />
      {error && <div className="message error" role="alert">{error}</div>}
      <section className="content-section settings-section">
        <div><span className="section-label">Apresentação</span><h2>Evidências</h2><p>Os dados completos continuam armazenados mesmo quando a interface mostra apenas o resumo.</p></div>
        <label className="switch-row" htmlFor="showFullEvidence">
          <span><strong>Exibir detalhes completos</strong><small>Inclui o resultado técnico estruturado na tela.</small></span>
          <input id="showFullEvidence" type="checkbox" checked={showFullEvidence} onChange={(event) => setShowFullEvidence(event.target.checked)} />
        </label>
      </section>
      <section className="content-section">
        <div className="section-heading"><div><span className="section-label">Integrações</span><h2>Modelos e agentes</h2></div>{catalog?.development_mode && <span className="status-badge warning">Recursos locais experimentais habilitados</span>}</div>
        <div id="agentList"><AgentList agents={agents} loading={loading} /></div>
      </section>
      <section className="content-section technical-note">
        <span className="section-label">Detalhes técnicos</span>
        <dl><div><dt>Ambiente</dt><dd>{catalog?.development_mode ? 'Desenvolvimento' : 'Produção'}</dd></div><div><dt>Modelo padrão</dt><dd>{catalog?.default_model || 'Não informado'}</dd></div></dl>
      </section>
    </div>
  );
}
