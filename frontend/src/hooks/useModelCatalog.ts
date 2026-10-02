import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { Agent, AgentCatalog, SelectedModel } from '../types';

const STORAGE_KEY = 'perito.selectedModel';

export function useModelCatalog() {
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [selectedValue, setSelectedValueState] = useState(() => localStorage.getItem(STORAGE_KEY) || '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const payload = await api.getAgents();
      setCatalog(payload);
      setSelectedValueState((current) => current || payload.default_model);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Não foi possível consultar os modelos.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const models = useMemo<SelectedModel[]>(() => {
    if (!catalog) return [];
    const items: SelectedModel[] = (catalog.models || []).map((model) => ({
      value: model, provider: 'gemini', model, label: model, available: true, experimental: false,
    }));
    for (const model of catalog.local_models || []) {
      items.push({
        value: `lmstudio:${model}`, provider: 'lmstudio', model,
        label: `LM Studio: ${model} (experimental)`, available: true, experimental: true,
      });
    }
    if (selectedValue && !items.some((item) => item.value === selectedValue)) {
      items.push({
        value: selectedValue,
        provider: selectedValue.startsWith('lmstudio:') ? 'lmstudio' : 'gemini',
        model: selectedValue.replace(/^lmstudio:/, ''),
        label: `${selectedValue} (indisponível)`, available: false,
        experimental: selectedValue.startsWith('lmstudio:'),
      });
    }
    return items;
  }, [catalog, selectedValue]);

  const selected = models.find((item) => item.value === selectedValue) || null;
  const setSelectedValue = (value: string) => {
    localStorage.setItem(STORAGE_KEY, value);
    setSelectedValueState(value);
  };

  const agents = useMemo<Agent[]>(() => {
    if (!catalog) return [];
    if (!catalog.catalog) return catalog.agents || [];
    return catalog.catalog.map((entry) => ({
      name: `${entry.provider}: ${entry.model}`,
      available: entry.provider === 'gemini' ? Boolean(entry.configured) : entry.loaded === true && entry.vision === true,
      state: entry.last_check ? (entry.last_check.passed ? 'Teste aprovado' : 'Teste falhou') : 'Não validado',
      detail: [
        entry.server,
        `visão: ${entry.vision === true ? 'sim' : entry.vision === false ? 'não' : 'desconhecida'}`,
        entry.loaded === null || entry.loaded === undefined ? '' : (entry.loaded ? 'carregado' : 'descarregado'),
        entry.last_check?.checked_at,
        entry.last_check?.error,
      ].filter(Boolean).join(' | '),
    }));
  }, [catalog]);

  return { catalog, models, selected, selectedValue, setSelectedValue, agents, loading, error, refresh };
}
