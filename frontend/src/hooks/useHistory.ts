import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { HistoryResponse } from '../types';

const empty: HistoryResponse = {
  history: [],
  models: [],
  pagination: { page: 1, total_pages: 1, total: 0, total_all: 0, page_size: 8, start: 0, end: 0, counts: {} },
};

export function useHistory(active = true) {
  const [tab, setTab] = useState('all');
  const [page, setPage] = useState(1);
  const [model, setModel] = useState('');
  const [data, setData] = useState<HistoryResponse>(empty);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!active) return;
    setLoading(true);
    setError('');
    try {
      const payload = await api.getHistory(tab, page, model);
      setData(payload);
      if (payload.pagination.page !== page) setPage(payload.pagination.page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Não foi possível carregar o histórico.');
    } finally {
      setLoading(false);
    }
  }, [active, model, page, tab]);

  useEffect(() => { void refresh(); }, [refresh]);

  const changeTab = (value: string) => { setTab(value); setPage(1); };
  const changeModel = (value: string) => { setModel(value); setPage(1); };

  return { tab, page, model, data, loading, error, setPage, changeTab, changeModel, refresh };
}
