const form = document.getElementById('form');
    const input = document.getElementById('image');
    const originalInput = document.getElementById('originalImage');
    const preview = document.getElementById('preview');
    const originalPreview = document.getElementById('originalPreview');
    const submit = document.getElementById('submit');
    const markReal = document.getElementById('markReal');
    const markModified = document.getElementById('markModified');
    const markAi = document.getElementById('markAi');
    const statusBox = document.getElementById('status');
    const thinking = document.getElementById('thinking');
    const phase = document.getElementById('phase');
    const percent = document.getElementById('percent');
    const barFill = document.getElementById('barFill');
    const steps = [
      document.getElementById('stepUpload'),
      document.getElementById('stepVision'),
      document.getElementById('stepReport')
    ];
    const result = document.getElementById('result');
    const verdict = document.getElementById('verdict');
    const report = document.getElementById('report');
    const forensics = document.getElementById('forensics');
    const forensicScore = document.getElementById('forensicScore');
    const forensicSource = document.getElementById('forensicSource');
    const forensicQuality = document.getElementById('forensicQuality');
    const forensicAudit = document.getElementById('forensicAudit');
    const forensicEvidence = document.getElementById('forensicEvidence');
    const historyTabs = document.getElementById('historyTabs');
    const historyList = document.getElementById('historyList');
    const historyCount = document.getElementById('historyCount');
    const historyRange = document.getElementById('historyRange');
    const historyPageLabel = document.getElementById('historyPageLabel');
    const historyPrev = document.getElementById('historyPrev');
    const historyNext = document.getElementById('historyNext');
    const navItems = Array.from(document.querySelectorAll('[data-page]'));
    const pages = Array.from(document.querySelectorAll('[data-page-panel]'));
    const dashTotal = document.getElementById('dashTotal');
    const dashModified = document.getElementById('dashModified');
    const dashReal = document.getElementById('dashReal');
    const dashInconclusive = document.getElementById('dashInconclusive');
    const dashboardAgents = document.getElementById('dashboardAgents');
    const showFullEvidenceInput = document.getElementById('showFullEvidence');
    const modelSelect = document.getElementById('modelSelect');
    const agentList = document.getElementById('agentList');
    let progressTimer = null;
    let progressValue = 0;
    let estimatedSeconds = 75;
    let progressStartedAt = 0;
    let activeHistoryTab = 'all';
    let historyPage = 1;
    let lastResultPayload = null;
    let showFullEvidence = localStorage.getItem('perito.showFullEvidence') === '1';
    let activeJob = sessionStorage.getItem('perito.activeJob');
    if (!/^[a-f0-9]{32}$/.test(activeJob || '')) activeJob = null;
    let submitting = false;
    let monitoring = false;
    let historyMeta = {
      page: 1,
      total_pages: 1,
      total: 0,
      total_all: 0,
      page_size: 8,
      start: 0,
      end: 0,
      counts: {}
    };

    showFullEvidenceInput.checked = showFullEvidence;

    function setActivePage(pageName) {
      navItems.forEach((item) => {
        item.classList.toggle('active', item.dataset.page === pageName);
      });
      pages.forEach((page) => {
        page.classList.toggle('active', page.dataset.pagePanel === pageName);
      });
      if (pageName === 'history' || pageName === 'dashboard') loadHistory();
      if (pageName === 'settings' || pageName === 'dashboard') loadAgents();
    }

    function setProgress(value, label) {
      progressValue = Math.max(progressValue, Math.min(value, 100));
      percent.textContent = `${Math.round(progressValue)}%`;
      barFill.style.width = `${progressValue}%`;
      phase.textContent = label;

      steps.forEach((step) => {
        step.classList.remove('active', 'done');
      });
      if (progressValue < 25) {
        steps[0].classList.add('active');
      } else if (progressValue < 86) {
        steps[0].classList.add('done');
        steps[1].classList.add('active');
      } else if (progressValue < 100) {
        steps[0].classList.add('done');
        steps[1].classList.add('done');
        steps[2].classList.add('active');
      } else {
        steps.forEach((step) => step.classList.add('done'));
      }
    }

    function startThinking() {
      thinking.classList.add('active');
      progressValue = 0;
      progressStartedAt = performance.now();
      setProgress(4, 'Enviando imagem para analise...');
      clearInterval(progressTimer);
      progressTimer = setInterval(() => {
        const elapsedSeconds = (performance.now() - progressStartedAt) / 1000;
        const ratio = Math.min(elapsedSeconds / Math.max(estimatedSeconds, 8), 1);
        let next = 8 + (ratio * 86);
        let label = 'Pericia local analisando evidencias visuais...';

        if (elapsedSeconds < 2) {
          next = Math.max(progressValue, 8);
          label = 'Preparando imagem e evidencias...';
        } else if (ratio < 0.72) {
          label = `Pericia local, LLM e auditoria CRAG (${Math.round(elapsedSeconds)}s de ~${Math.round(estimatedSeconds)}s)...`;
        } else if (ratio < 0.96) {
          label = 'Normalizando score, confianca e justificativa...';
        } else {
          next = Math.min(97, next);
          label = 'Finalizando veredito...';
        }

        setProgress(Math.min(next, 97), label);
      }, 1000);
    }

    function finishThinking(label) {
      clearInterval(progressTimer);
      progressTimer = null;
      setProgress(100, label);
    }

    function resetThinking() {
      clearInterval(progressTimer);
      progressTimer = null;
      progressValue = 0;
      thinking.classList.remove('active');
      setProgress(0, 'Aguardando envio');
    }

    function verdictClass(value) {
      const normalized = String(value || '').toLowerCase();
      if (normalized.includes('ia') || normalized.includes('alterada') || normalized.includes('modificado') || normalized.includes('edicao')) return 'sim';
      if (normalized.includes('real')) return 'nao';
      if (normalized.includes('sim')) return 'sim';
      if (normalized.includes('nao') || normalized.includes('não')) return 'nao';
      return 'indeterminado';
    }

    function qualityText(payload) {
      const metrics = payload.forensic_metrics || {};
      const status = String(payload.forensic_quality || metrics.quality_status || '').trim();
      if (!status) return '-';
      const labels = {
        boa: 'boa',
        limitada: 'limitada',
        insuficiente: 'insuficiente'
      };
      const label = labels[status.toLowerCase()] || status;
      if (status.toLowerCase() === 'insuficiente') {
        return 'insuficiente - resolucao/nitidez insuficiente para pericia confiavel';
      }
      return label;
    }

    function auditText(payload) {
      const status = String(payload.audit_status || '').trim();
      if (!status || status === 'nao_executada') return '-';
      const evidence = Array.isArray(payload.audit_evidence)
        ? payload.audit_evidence.filter(Boolean).slice(0, 2).join('; ')
        : '';
      if (!evidence) return status;
      return `${status} - ${evidence}`;
    }

    function firstReportValue(reportText, label) {
      const regex = new RegExp(`^${label}:\s*(.+)$`, 'im');
      const match = String(reportText || '').match(regex);
      return match ? match[1].trim() : '';
    }

    function truncateText(text, maxLength) {
      const clean = String(text || '').replace(/\s+/g, ' ').trim();
      if (clean.length <= maxLength) return clean;
      return `${clean.slice(0, maxLength - 3).trim()}...`;
    }

    function evidenceSummary(payload) {
      const evidenceText = Array.isArray(payload.forensic_evidence)
        ? payload.forensic_evidence.filter(Boolean).join('; ')
        : String(payload.forensic_evidence || '');
      const source = evidenceText || firstReportValue(payload.report, 'EVIDENCIAS');
      const conciseSource = source
        .replace(/qualidade limitada; conclusao exige cautela:\s*/i, '')
        .replace(/qualidade insuficiente para pericia visual confiavel:\s*/i, '');
      const parts = conciseSource
        .split(';')
        .map((part) => part.trim())
        .filter(Boolean)
        .filter((part) => !/proximo de exemplo calibrado:/i.test(part))
        .filter((part) => !(/resolucao.*megapixel/i.test(part) && /menor lado abaixo de/i.test(source)))
        .map((part) => part
          .replace(/resolucao (limitada|baixa): menor lado abaixo de (\d+) px/i, 'resolucao $1 (<$2 px)')
          .replace(/nitidez inconsistente entre regioes, com contraste fino.*$/i, 'nitidez inconsistente entre regioes')
          .replace(/ruido local inconsistente, indicando.*$/i, 'ruido varia entre areas, com possivel processamento desigual')
          .replace(/mapa de nitidez e ruido aponta transicoes regionais pouco uniformes/i, 'transicoes irregulares de nitidez e ruido')
          .replace(/, com cor artificial destoando do padrao odontologico da imagem/i, '')
          .replace(/, sugerindo anotacao manual ou edicao grafica aplicada sobre a imagem/i, ' (possivel anotacao ou edicao)')
          .replace(/imagem apresenta alto nivel de detalhe e ruido, exigindo cautela para diferenciar textura real de artefato/i, 'detalhe e ruido elevados dificultam distinguir textura de artefatos'))
        .filter((part, index, list) => list.findIndex((item) => item.toLowerCase() === part.toLowerCase()) === index)
        .sort((a, b) => Number(/^(resolucao|qualidade)/i.test(a)) - Number(/^(resolucao|qualidade)/i.test(b)))
        .slice(0, 3);
      const summary = parts.map((part) => truncateText(part, 100)).join('; ');
      return truncateText(summary || source || '-', 220);
    }

    function fullEvidenceText(payload) {
      return Array.isArray(payload.forensic_evidence)
        ? payload.forensic_evidence.filter(Boolean).join('; ')
        : String(payload.forensic_evidence || '');
    }

    function visibleEvidenceText(payload) {
      return showFullEvidence ? (fullEvidenceText(payload) || '-') : evidenceSummary(payload);
    }

    function compactReportText(payload, includeEvidence = true) {
      const reportText = String(payload.report || '');
      const confidence = firstReportValue(reportText, 'CONFIANCA');
      const justification = firstReportValue(reportText, 'JUSTIFICATIVA');
      const lines = [];

      if (justification) lines.push(`Justificativa: ${justification}`);
      if (confidence) lines.push(`Confianca: ${confidence}`);
      if (includeEvidence) lines.push(`Evidencias: ${evidenceSummary(payload)}`);
      return lines.join('\n');
    }

    function visibleReportText(payload, includeEvidence = true) {
      if (payload.schema_version === '2.0') {
        if (showFullEvidence) return JSON.stringify(payload, null, 2);
        if (payload.status === 'nao_concluida') return payload.error || payload.report || 'Analise nao concluida.';
        const analysis = payload.structured_result || {};
        const lines = [analysis.justificativa || payload.report || ''];
        if (includeEvidence) lines.push(`Evidencias: ${evidenceSummary(payload)}`);
        if (analysis.limitacoes && analysis.limitacoes.length) lines.push(`Limitacoes: ${analysis.limitacoes.slice(0, 2).join(' ')}`);
        return lines.join('\n');
      }
      return showFullEvidence ? (payload.report || compactReportText(payload)) : compactReportText(payload, includeEvidence);
    }

    function renderResultPayload(payload) {
      lastResultPayload = payload;
      verdict.textContent = payload.status === 'nao_concluida' ? 'Analise nao concluida' : (payload.status === 'experimental' || payload.experimental) ? `Teste local: ${payload.verdict}` : `Veredito: ${payload.verdict}`;
      verdict.className = `verdict ${verdictClass(payload.verdict)}`;
      report.textContent = visibleReportText(payload, false);
      report.dataset.fullReport = payload.report || '';
      forensicScore.parentElement.hidden = payload.schema_version === '2.0';
      forensicScore.textContent = payload.forensic_score != null ? `${payload.forensic_score}%` : '-';
      forensicSource.textContent = payload.source || '-';
      forensicQuality.textContent = qualityText(payload);
      forensicAudit.textContent = auditText(payload);
      forensicEvidence.textContent = visibleEvidenceText(payload);
      forensicEvidence.title = fullEvidenceText(payload);
      forensics.style.display = 'grid';
      result.style.display = 'block';
    }

    function isModifiedHistory(item) {
      const verdict = String(item.verdict || '').toUpperCase();
      return verdict.includes('MODIFICADO') || verdict.includes('ALTERADA') || verdict.includes('IA') || verdict.includes('EDICAO');
    }

    function isCalibrationHistory(item) {
      const source = String(item.source || '').toLowerCase();
      const model = String(item.model || '').toLowerCase();
      return source.includes('calibracao') || source.includes('feedback') || model.includes('calibracao');
    }

    function updateHistoryTabs(counts) {
      historyTabs.querySelectorAll('.history-tab').forEach((tab) => {
        const tabName = tab.dataset.tab;
        tab.classList.toggle('active', tabName === activeHistoryTab);
        const counter = tab.querySelector('.history-tab-count');
        if (counter) counter.textContent = counts[tabName] || 0;
      });
    }

    function emptyHistoryMessage() {
      const labels = {
        all: 'Nenhuma analise armazenada ainda.',
        modified: 'Nenhuma analise modificada ou IA nesta aba.',
        real: 'Nenhuma analise real nesta aba.',
        inconclusive: 'Nenhuma analise inconclusiva nesta aba.',
        calibration: 'Nenhuma calibracao salva nesta aba.'
      };
      return labels[activeHistoryTab] || labels.all;
    }

    function updateHistoryPager(meta) {
      historyMeta = {
        page: Number(meta.page || 1),
        total_pages: Math.max(1, Number(meta.total_pages || 1)),
        total: Number(meta.total || 0),
        total_all: Number(meta.total_all || 0),
        page_size: Number(meta.page_size || 8),
        start: Number(meta.start || 0),
        end: Number(meta.end || 0),
        counts: meta.counts || {}
      };

      const totalLabel = historyMeta.total_all === 1 ? 'registro' : 'registros';
      const tabTotalLabel = historyMeta.total === 1 ? 'registro nesta aba' : 'registros nesta aba';
      historyCount.textContent = `${historyMeta.total_all} ${totalLabel}`;
      historyRange.textContent = historyMeta.total
        ? `${historyMeta.start}-${historyMeta.end} de ${historyMeta.total} ${tabTotalLabel}`
        : `0 de ${historyMeta.total} registros nesta aba`;
      historyPageLabel.textContent = `Pagina ${historyMeta.page} / ${historyMeta.total_pages}`;
      historyPrev.disabled = historyMeta.page <= 1;
      historyNext.disabled = historyMeta.page >= historyMeta.total_pages;
      updateHistoryTabs(historyMeta.counts);
      dashTotal.textContent = historyMeta.total_all || 0;
      dashModified.textContent = historyMeta.counts.modified || 0;
      dashReal.textContent = historyMeta.counts.real || 0;
      dashInconclusive.textContent = historyMeta.counts.inconclusive || 0;
    }

    function renderAgents(payload) {
      document.querySelectorAll('[data-development-only]').forEach((element) => { element.hidden = !payload.development_mode; });
      const agents = payload.catalog ? payload.catalog.map(entry => ({
        name: entry.provider + ': ' + entry.model,
        available: entry.provider === 'gemini' ? entry.configured : entry.loaded && entry.vision === true,
        state: entry.last_check ? (entry.last_check.passed ? 'teste aprovado' : 'teste falhou') : 'nao validado',
        detail: entry.server + ' | visao: ' + (entry.vision === true ? 'sim' : entry.vision === false ? 'nao' : 'desconhecida') +
          (entry.loaded === null ? '' : ' | ' + (entry.loaded ? 'carregado' : 'descarregado')) +
          (entry.last_check ? ' | ' + entry.last_check.checked_at + (entry.last_check.error ? ' | ' + entry.last_check.error : '') : '')
      })) : (payload.agents || []);
      const savedModel = localStorage.getItem('perito.selectedModel') || payload.default_model;
      modelSelect.replaceChildren();
      for (const model of payload.models || []) {
        modelSelect.add(new Option(model, model));
      }
      for (const model of payload.local_models || []) {
        modelSelect.add(new Option('LM Studio: ' + model + ' (experimental)', 'lmstudio:' + model));
      }
      const missingSelection = !Array.from(modelSelect.options).some(option => option.value === savedModel);
      if (missingSelection && savedModel) {
        const unavailable = new Option(savedModel + ' (indisponivel)', savedModel);
        unavailable.disabled = true;
        modelSelect.add(unavailable);
      }
      modelSelect.value = savedModel || payload.default_model;
      modelSelect.disabled = modelSelect.options.length === 0;
      submit.disabled = submitting || Boolean(activeJob) || missingSelection;
      document.getElementById('modelStatus').textContent = missingSelection ? 'Modelo escolhido indisponivel. Selecione outro modelo ou atualize a lista.' : (payload.lmstudio_status || '');
      for (const container of [agentList, dashboardAgents]) {
        container.replaceChildren();
        for (const agent of agents) {
          const row = document.createElement('div');
          row.className = 'agent-item';
          const description = document.createElement('div');
          const name = document.createElement('strong');
          name.textContent = agent.name;
          const detail = document.createElement('small');
          detail.textContent = agent.detail || '';
          description.append(name, document.createElement('br'), detail);
          const badge = document.createElement('span');
          badge.className = 'agent-badge' + (agent.available ? '' : ' off');
          badge.textContent = agent.state || (agent.available ? 'disponivel' : 'indisponivel');
          row.append(description, badge);
          container.append(row);
        }
      }
    }

    function renderHistory(payload) {
      const items = payload.history || [];
      const filter = document.getElementById('historyModel');
      if (payload.models) {
        const selected = filter.value;
        filter.replaceChildren(new Option('Todos os modelos', ''));
        for (const model of payload.models) filter.add(new Option(model, model));
        filter.value = payload.models.includes(selected) ? selected : '';
      }
      updateHistoryPager(payload.pagination || {});
      if (!items.length) {
        historyList.innerHTML = `<div class="history-empty">${emptyHistoryMessage()}</div>`;
        return;
      }

      historyList.innerHTML = '';
      for (const item of items) {
        const card = document.createElement('article');
        card.className = 'history-item';

        const imageBox = document.createElement('div');
        imageBox.className = 'history-images';

        const image = document.createElement('img');
        image.src = item.image_url;
        image.alt = item.filename || 'Imagem analisada';
        image.loading = 'lazy';
        imageBox.appendChild(image);

        if (item.original_image_url) {
          const originalImage = document.createElement('img');
          originalImage.className = 'original-thumb';
          originalImage.src = item.original_image_url;
          originalImage.alt = item.original_filename || 'Imagem original';
          originalImage.loading = 'lazy';
          imageBox.appendChild(originalImage);
        }

        const body = document.createElement('div');
        const meta = document.createElement('div');
        meta.className = 'history-meta';
        const duration = item.duration_seconds ? ` · ${item.duration_seconds}s` : '';
        meta.textContent = `${item.created_at || ''} · ${item.filename || ''}${duration}`;

        const score = item.forensic_score !== undefined && item.forensic_score !== null ? ` - score ${item.forensic_score}` : '';
        const source = item.source ? ` - ${item.source}` : '';
        const quality = item.forensic_quality ? ` - qualidade ${item.forensic_quality}` : '';
        const audit = item.audit_status && item.audit_status !== 'nao_executada' ? ` - auditoria ${item.audit_status}` : '';
        meta.textContent = `${meta.textContent}${score}${quality}${audit}${source}`;

        const itemVerdict = document.createElement('div');
        itemVerdict.className = `history-verdict ${verdictClass(item.verdict)}`;
        itemVerdict.textContent = item.status === 'nao_concluida' ? 'Analise nao concluida' : (item.status === 'experimental' || item.experimental) ? `Teste local: ${item.verdict}` : `Veredito: ${item.verdict || 'INDETERMINADO'}`;

        const itemReport = document.createElement('div');
        itemReport.className = 'history-report';
        itemReport.textContent = visibleReportText(item);
        itemReport.title = item.report || '';

        body.append(meta, itemVerdict, itemReport);
        const actions = document.createElement('div');
        actions.className = 'actions';
        if (item.original_image_url) {
          const compare = document.createElement('button');
          compare.type = 'button';
          compare.textContent = 'Comparar';
          compare.addEventListener('click', () => {
            document.getElementById('compareReference').src = item.original_image_url;
            document.getElementById('compareAnalyzed').src = item.image_url;
            document.getElementById('comparisonDialog').showModal();
          });
          actions.append(compare);
        }
        if (item.analysis_id) {
          const download = document.createElement('a');
          download.href = '/analysis/' + encodeURIComponent(item.analysis_id) + '/export';
          download.download = 'analysis-' + item.analysis_id + '.json';
          download.textContent = 'Exportar evidencias';
          actions.append(download);
        }
        body.append(actions);
        card.append(imageBox, body);
        historyList.appendChild(card);
      }
    }

    historyTabs.addEventListener('click', (event) => {
      const tab = event.target.closest('.history-tab');
      if (!tab) return;
      activeHistoryTab = tab.dataset.tab || 'all';
      historyPage = 1;
      loadHistory();
    });
    document.getElementById('historyModel').addEventListener('change', () => { historyPage = 1; loadHistory(); });
    document.getElementById('closeComparison').addEventListener('click', () => document.getElementById('comparisonDialog').close());

    historyPrev.addEventListener('click', () => {
      if (historyMeta.page <= 1) return;
      historyPage = historyMeta.page - 1;
      loadHistory();
    });

    historyNext.addEventListener('click', () => {
      if (historyMeta.page >= historyMeta.total_pages) return;
      historyPage = historyMeta.page + 1;
      loadHistory();
    });

    async function calibrateImage(label) {
      const input = document.getElementById('calibrationImage');
      const originalInput = document.getElementById('calibrationOriginal');
      const statusBox = document.getElementById('calibrationStatus');
      const file = input.files[0];
      if (!file) {
        statusBox.textContent = 'Selecione uma imagem antes de marcar como exemplo.';
        return;
      }

      if (!window.confirm('Salvar este rotulo fornecido por voce na calibracao?')) return;
      markReal.disabled = true;
      markModified.disabled = true;
      markAi.disabled = true;
      result.style.display = 'none';
      forensics.style.display = 'none';
      resetThinking();
      const statusByLabel = {
        REAL: 'Salvando exemplo local como real...',
        MODIFICADO: 'Salvando exemplo local como modificado...',
        IA_GERADA_EDITADA: 'Salvando exemplo local como IA/editada...'
      };
      statusBox.textContent = statusByLabel[label] || 'Salvando exemplo local...';

      const data = new FormData();
      data.append('image', file);
      data.append('label', label);
      if (originalInput.files[0]) {
        data.append('original_image', originalInput.files[0]);
      }

      try {
        const response = await fetch('/calibrate', { method: 'POST', body: data });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Falha ao salvar exemplo.');


        statusBox.textContent = 'Exemplo de calibracao salvo.';
        historyPage = 1;
        await loadHistory();
      } catch (error) {
        statusBox.textContent = error.message;
      } finally {

        markReal.disabled = false;
        markModified.disabled = false;
        markAi.disabled = false;
      }
    }

    async function loadHistory() {
      try {
        const params = new URLSearchParams({
          tab: activeHistoryTab,
          model: document.getElementById('historyModel').value,
          page: String(historyPage)
        });
        const response = await fetch(`/history?${params.toString()}`);
        if (!response.ok) return;
        const payload = await response.json();
        if (showFullEvidence && payload.history) {
          payload.history = await Promise.all(payload.history.map(async (item) => {
            if (!item.analysis_id) return item;
            try {
              const detail = await fetch(`/analysis/${encodeURIComponent(item.analysis_id)}`);
              return detail.ok ? { ...item, ...await detail.json() } : item;
            } catch (_) { return item; }
          }));
        }
        renderHistory(payload);
      } catch (_error) {
        historyList.innerHTML = '<div class="history-empty">Nao foi possivel carregar o historico.</div>';
      }
    }

    async function loadMetrics() {
      try {
        const response = await fetch('/metrics');
        if (!response.ok) return;
        const payload = await response.json();
        if (payload.estimated_seconds) {
          estimatedSeconds = Math.max(8, Number(payload.estimated_seconds));
        }
      } catch (_error) {
        estimatedSeconds = 75;
      }
    }

    async function loadAgents() {
      try {
        const response = await fetch('/agents');
        if (!response.ok) return;
        const payload = await response.json();
        renderAgents(payload);
      } catch (_error) {
        const fallback = '<div class="agent-item">Nao foi possivel carregar agentes.</div>';
        agentList.innerHTML = fallback;
        dashboardAgents.innerHTML = fallback;
      }
    }

    navItems.forEach((item) => {
      item.addEventListener('click', () => setActivePage(item.dataset.page || 'analyze'));
    });

    showFullEvidenceInput.addEventListener('change', () => {
      showFullEvidence = showFullEvidenceInput.checked;
      localStorage.setItem('perito.showFullEvidence', showFullEvidence ? '1' : '0');
      if (lastResultPayload) renderResultPayload(lastResultPayload);
      renderHistory({ history: [], pagination: historyMeta });
      loadHistory();
    });

    modelSelect.addEventListener('change', () => {
      localStorage.setItem('perito.selectedModel', modelSelect.value);
      updateAnalysisControls();
    });
    document.getElementById('refreshModels').addEventListener('click', async (event) => {
      event.target.disabled = true;
      try {
        const response = await fetch('/agents');
        if (!response.ok) throw new Error('Falha ao atualizar modelos.');
        renderAgents(await response.json());
      } catch (error) {
        document.getElementById('modelStatus').textContent = error.message;
      } finally { event.target.disabled = false; }
    });

    input.addEventListener('change', () => {
      const file = input.files[0];
      result.style.display = 'none';
      forensics.style.display = 'none';
      resetThinking();
      if (!file) {
        preview.style.display = 'none';
        return;
      }
      preview.src = URL.createObjectURL(file);
      preview.style.display = 'block';
    });

    originalInput.addEventListener('change', () => {
      const file = originalInput.files[0];
      result.style.display = 'none';
      forensics.style.display = 'none';
      resetThinking();
      if (!file) {
        originalPreview.style.display = 'none';
        return;
      }
      originalPreview.src = URL.createObjectURL(file);
      originalPreview.style.display = 'block';
    });

    markReal.addEventListener('click', () => calibrateImage('REAL'));
    markModified.addEventListener('click', () => calibrateImage('MODIFICADO'));
    markAi.addEventListener('click', () => calibrateImage('IA_GERADA_EDITADA'));

    function updateAnalysisControls() {
      const busy = submitting || Boolean(activeJob);
      submit.disabled = busy || !modelSelect.value || Boolean(modelSelect.selectedOptions[0]?.disabled);
      input.disabled = originalInput.disabled = busy;
      markReal.disabled = markModified.disabled = markAi.disabled = busy;
      document.getElementById('cancelAnalysis').hidden = !activeJob;
      document.getElementById('resumeAnalysis').hidden = !activeJob || monitoring;
    }

    function clearActiveJob() {
      activeJob = null;
      sessionStorage.removeItem('perito.activeJob');
    }

    async function showAnalysisResult(payload) {
      renderResultPayload(payload);
      finishThinking(payload.status === 'nao_concluida' ? 'Analise nao concluida.' : 'Resposta pronta.');
      statusBox.textContent = payload.status === 'nao_concluida' ? 'Evidencias preservadas. A analise pode ser tentada novamente.' : payload.duration_seconds
        ? `Analise concluida em ${payload.duration_seconds}s.` : 'Analise concluida.';
      historyPage = 1;
      await loadHistory();
    }

    async function monitorAnalysis() {
      if (!activeJob || monitoring) return;
      monitoring = true;
      updateAnalysisControls();
      startThinking();
      try {
        for (;;) {
          const response = await fetch('/jobs/' + activeJob);
          if (response.status === 404) {
            clearActiveJob();
            throw new Error('Analise nao encontrada no servidor. Consulte o historico.');
          }
          if (!response.ok) throw new Error('Falha ao consultar a analise.');
          const job = await response.json();
          statusBox.textContent = ({ aguardando: 'Na fila', executando: 'Analisando', cancelando: 'Cancelamento solicitado' })[job.state] || job.state;
          if (['concluida', 'falhou', 'cancelada'].includes(job.state)) {
            clearActiveJob();
            if (job.state === 'cancelada') throw new Error('Analise cancelada.');
            if (!job.result) throw new Error(job.error || 'Falha na analise.');
            await showAnalysisResult(job.result);
            return;
          }
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      } catch (error) {
        clearInterval(progressTimer);
        statusBox.textContent = activeJob ? 'Conexao interrompida. A analise permanece no servidor.' : error.message;
      } finally {
        monitoring = false;
        updateAnalysisControls();
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (submitting || activeJob) return;
      const file = input.files[0];
      if (!file) return;
      if (!modelSelect.value || modelSelect.selectedOptions[0]?.disabled) {
        statusBox.textContent = 'Selecione um modelo disponivel.';
        return;
      }

      submitting = true;
      updateAnalysisControls();
      statusBox.textContent = 'Enviando para analise...';
      result.style.display = 'none';
      forensics.style.display = 'none';
      await loadMetrics();
      startThinking();

      const data = new FormData();
      data.append('image', file);
      if (originalInput.files[0]) {
        data.append('original_image', originalInput.files[0]);
      }
      {
        data.append('use_llm', '1');
        const localModel = modelSelect.value.startsWith('lmstudio:');
        data.append('agent_provider', localModel ? 'lmstudio' : 'gemini');
        data.append('model', localModel ? modelSelect.value.slice(9) : modelSelect.value);
      }

      try {
        const response = await fetch('/analyze', { method: 'POST', headers: { Prefer: 'respond-async' }, body: data });
        let payload = await response.json();
        if (response.status === 202) {
          if (!/^[a-f0-9]{32}$/.test(payload.job_id || '')) throw new Error('Identificador de analise invalido.');
          activeJob = payload.job_id;
          sessionStorage.setItem('perito.activeJob', activeJob);
          await monitorAnalysis();
          return;
        }
        if (!response.ok && payload.status !== 'nao_concluida') throw new Error(payload.error || 'Falha na analise.');
        await showAnalysisResult(payload);
      } catch (error) {
        clearInterval(progressTimer);
        statusBox.textContent = error.message;
      } finally {
        submitting = false;
        updateAnalysisControls();
      }
    });

    document.getElementById('cancelAnalysis').addEventListener('click', async () => {
      if (!activeJob) return;
      try {
        const response = await fetch('/jobs/' + activeJob + '/cancel', { method: 'POST' });
        statusBox.textContent = response.ok ? 'Cancelamento solicitado.' : 'Falha ao solicitar cancelamento.';
        if (response.ok && !monitoring) await monitorAnalysis();
      } catch (error) {
        statusBox.textContent = 'Sem conexao. O cancelamento nao foi confirmado.';
      }
    });
    document.getElementById('resumeAnalysis').addEventListener('click', monitorAnalysis);
    if (activeJob) monitorAnalysis();
    loadHistory();
    loadMetrics();
    loadAgents();
