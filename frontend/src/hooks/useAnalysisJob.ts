import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { AnalysisResult } from '../types';

const JOB_KEY = 'perito.activeJob';
const validJob = (value: string | null) => value && /^[a-f0-9]{32}$/.test(value) ? value : null;

export function useAnalysisJob(onComplete: () => void) {
  const [jobId, setJobId] = useState<string | null>(() => validJob(sessionStorage.getItem(JOB_KEY)));
  const [state, setState] = useState<string>(() => jobId ? 'aguardando' : 'ociosa');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const [connectionLost, setConnectionLost] = useState(false);
  const monitoring = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const clearJob = useCallback(() => {
    sessionStorage.removeItem(JOB_KEY);
    setJobId(null);
  }, []);

  const monitor = useCallback(async (explicitId?: string) => {
    const id = explicitId || jobId;
    if (!id || monitoring.current) return;
    monitoring.current = true;
    setConnectionLost(false);
    setError('');
    try {
      for (;;) {
        const job = await api.getJob(id);
        if (!mounted.current) return;
        setState(job.state);
        if (job.state === 'cancelada') {
          clearJob();
          setError('Análise cancelada.');
          return;
        }
        if (job.state === 'falhou') {
          clearJob();
          setError(job.error || 'A análise falhou antes de produzir um resultado.');
          return;
        }
        if (job.state === 'concluida') {
          clearJob();
          if (!job.result) throw new Error('O servidor concluiu a tarefa sem retornar o resultado.');
          setResult(job.result);
          setState(job.result.status || 'concluida');
          onComplete();
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    } catch (reason) {
      if (!mounted.current) return;
      setConnectionLost(true);
      setError(reason instanceof Error ? reason.message : 'A conexão com o servidor foi interrompida.');
    } finally {
      monitoring.current = false;
    }
  }, [clearJob, jobId, onComplete]);

  useEffect(() => {
    if (jobId) void monitor(jobId);
  }, []); // Resume only once after the page is mounted.

  const submit = async (image: File, original: File | null, model: string) => {
    if (jobId) return;
    setResult(null);
    setError('');
    setConnectionLost(false);
    setState('enviando');
    try {
      const payload = await api.submitAnalysis(image, original, model);
      const returnedJobId = (payload as { job_id?: unknown }).job_id;
      if (typeof returnedJobId === 'string') {
        if (!validJob(returnedJobId)) throw new Error('O servidor retornou um identificador de análise inválido.');
        sessionStorage.setItem(JOB_KEY, returnedJobId);
        setJobId(returnedJobId);
        setState('aguardando');
        await monitor(returnedJobId);
      } else {
        const completed = payload as AnalysisResult;
        setResult(completed);
        setState(completed.status || 'concluida');
        onComplete();
      }
    } catch (reason) {
      setState('falhou');
      setError(reason instanceof Error ? reason.message : 'Não foi possível iniciar a análise.');
    }
  };

  const cancel = async () => {
    if (!jobId) return;
    try {
      const response = await api.cancelJob(jobId);
      setState(response.state);
      if (!monitoring.current) void monitor(jobId);
    } catch {
      setError('Sem conexão. O cancelamento não foi confirmado.');
    }
  };

  const busy = Boolean(jobId) || ['enviando', 'aguardando', 'executando', 'cancelando'].includes(state);
  return { jobId, state, result, error, connectionLost, busy, submit, cancel, resume: () => monitor() };
}
