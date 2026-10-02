export type PageName = 'dashboard' | 'analyze' | 'history' | 'settings' | 'calibration';

export interface CatalogEntry {
  provider: string;
  model: string;
  configured?: boolean;
  loaded?: boolean | null;
  vision?: boolean | null;
  server?: string;
  last_check?: { passed?: boolean; checked_at?: string; error?: string };
}

export interface Agent {
  name: string;
  available?: boolean;
  state?: string;
  detail?: string;
}

export interface AgentCatalog {
  development_mode: boolean;
  default_model: string;
  models: string[];
  local_models?: string[];
  catalog?: CatalogEntry[];
  agents?: Agent[];
  lmstudio_status?: string;
}

export interface AnalysisResult {
  analysis_id?: string;
  schema_version?: string;
  status?: string;
  experimental?: boolean;
  verdict?: string | null;
  report?: string;
  error?: string;
  error_code?: string;
  duration_seconds?: number;
  source?: string;
  model?: string;
  forensic_score?: number;
  forensic_quality?: string;
  forensic_evidence?: string[] | string;
  audit_status?: string;
  audit_evidence?: string[];
  forensic_metrics?: Record<string, unknown> & { quality_status?: string };
  structured_result?: {
    justificativa?: string;
    evidencias_favoraveis?: string[];
    evidencias_contrarias?: string[];
    limitacoes?: string[];
  };
  [key: string]: unknown;
}

export interface JobStatus {
  state: 'aguardando' | 'executando' | 'cancelando' | 'concluida' | 'falhou' | 'cancelada' | string;
  result?: AnalysisResult;
  error?: string;
}

export interface HistoryItem extends AnalysisResult {
  id?: string;
  created_at?: string;
  filename?: string;
  image_url?: string;
  original_image_url?: string;
}

export interface HistoryPagination {
  page: number;
  total_pages: number;
  total: number;
  total_all: number;
  page_size: number;
  start: number;
  end: number;
  counts: Record<string, number>;
}

export interface HistoryResponse {
  history: HistoryItem[];
  models: string[];
  pagination: HistoryPagination;
}

export interface SelectedModel {
  value: string;
  provider: 'gemini' | 'lmstudio';
  model: string;
  label: string;
  available: boolean;
  experimental: boolean;
}
