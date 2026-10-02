import type { Agent } from '../types';

export function AgentList({ agents, loading }: { agents: Agent[]; loading?: boolean }) {
  if (loading) return <div className="empty-state">Consultando modelos disponíveis...</div>;
  if (!agents.length) return <div className="empty-state">Nenhum agente foi informado pelo servidor.</div>;
  return (
    <div className="agent-list">
      {agents.map((agent) => (
        <div className="agent-item" key={agent.name}>
          <div>
            <strong>{agent.name}</strong>
            {agent.detail && <small>{agent.detail}</small>}
          </div>
          <span className={`status-badge ${agent.available ? 'success' : 'danger'}`}>
            <span aria-hidden="true">{agent.available ? '✓' : '!'}</span>
            {agent.state || (agent.available ? 'Disponível' : 'Indisponível')}
          </span>
        </div>
      ))}
    </div>
  );
}
