import type { AgentCatalog, AnalysisResult, HistoryResponse, JobStatus } from '../types';

async function parseJson<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Resposta inválida do servidor (${response.status}).`);
  }
  if (!response.ok) {
    const error = payload as { error?: string; message?: string; status?: string };
    if (error.status !== 'nao_concluida') {
      throw new Error(error.error || error.message || `Falha no servidor (${response.status}).`);
    }
  }
  return payload as T;
}

export const api = {
  async getAgents(): Promise<AgentCatalog> {
    return parseJson(await fetch('/agents'));
  },

  async getEstimate(): Promise<number | null> {
    const payload = await parseJson<{ estimated_seconds?: number }>(await fetch('/metrics'));
    return typeof payload.estimated_seconds === 'number' ? payload.estimated_seconds : null;
  },

  async getHistory(tab: string, page: number, model: string): Promise<HistoryResponse> {
    const query = new URLSearchParams({ tab, page: String(page), page_size: '8' });
    if (model) query.set('model', model);
    return parseJson(await fetch(`/history?${query}`));
  },

  async submitAnalysis(image: File, original: File | null, selected: string): Promise<{ job_id: string } | AnalysisResult> {
    const data = new FormData();
    data.append('image', image);
    if (original) data.append('original_image', original);
    const local = selected.startsWith('lmstudio:');
    data.append('use_llm', '1');
    data.append('agent_provider', local ? 'lmstudio' : 'gemini');
    data.append('model', local ? selected.slice('lmstudio:'.length) : selected);
    return parseJson(await fetch('/analyze', { method: 'POST', headers: { Prefer: 'respond-async' }, body: data }));
  },

  async getJob(id: string): Promise<JobStatus> {
    return parseJson(await fetch(`/jobs/${id}`));
  },

  async cancelJob(id: string): Promise<JobStatus> {
    return parseJson(await fetch(`/jobs/${id}/cancel`, { method: 'POST' }));
  },

  async calibrate(image: File, original: File | null, label: string): Promise<AnalysisResult> {
    const data = new FormData();
    data.append('image', image);
    if (original) data.append('original_image', original);
    data.append('label', label);
    return parseJson(await fetch('/calibrate', { method: 'POST', body: data }));
  },
};
