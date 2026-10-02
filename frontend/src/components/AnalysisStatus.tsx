import { LoaderCircle } from 'lucide-react';

const labels: Record<string, { title: string; detail: string; step: number }> = {
  enviando: { title: 'Enviando imagem', detail: 'Preparando os arquivos para o servidor.', step: 1 },
  aguardando: { title: 'Na fila', detail: 'A análise aguarda a execução no servidor.', step: 2 },
  executando: { title: 'Analisando evidências', detail: 'Perícia local, modelo e verificação das evidências em andamento.', step: 3 },
  cancelando: { title: 'Cancelamento solicitado', detail: 'Aguardando a confirmação do servidor.', step: 3 },
};

export function AnalysisStatus({ state, estimate }: { state: string; estimate: number | null }) {
  const current = labels[state];
  if (!current) return null;
  const steps = ['Upload recebido', 'Aguardando processamento', 'Análise e verificação'];
  return (
    <section id="thinking" className="analysis-status" aria-live="polite">
      <div className="status-current">
        <LoaderCircle className="spin" aria-hidden="true" size={20} />
        <div>
          <strong id="phase">{current.title}</strong>
          <span>{current.detail}</span>
        </div>
      </div>
      <ol className="server-steps">
        {steps.map((step, index) => (
          <li key={step} className={index + 1 < current.step ? 'done' : index + 1 === current.step ? 'active' : ''}>
            <span aria-hidden="true">{index + 1 < current.step ? '✓' : index + 1}</span>{step}
          </li>
        ))}
      </ol>
      {estimate && <p className="estimate">Duração estimada pelo servidor: cerca de {Math.round(estimate)} segundos.</p>}
    </section>
  );
}
