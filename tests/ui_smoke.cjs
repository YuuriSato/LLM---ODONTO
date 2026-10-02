const assert = require('node:assert/strict');
const fsSync = require('node:fs');
const fs = require('node:fs/promises');
const { spawn } = require('node:child_process');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const windowsVenv = path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe');
  const unixVenv = path.join(__dirname, '..', '.venv', 'bin', 'python');
  const testPython = process.env.TEST_PYTHON || (fsSync.existsSync(windowsVenv) ? windowsVenv : fsSync.existsSync(unixVenv) ? unixVenv : 'python');
  const server = spawn(testPython, ['-u', path.join(__dirname, 'ui_server.py')], { windowsHide: true });
  const serverClosed = new Promise(resolve => server.once('close', resolve));
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('UI fixture server did not start')), 20000);
      let output = '';
      server.on('error', error => { clearTimeout(timeout); reject(error); });
      server.once('exit', code => { clearTimeout(timeout); reject(new Error('UI fixture server exited: ' + code)); });
      server.stdout.on('data', data => {
        output += data;
        const match = output.match(/UI_TEST_URL=(http:\/\/127\.0\.0\.1:\d+)/);
        if (match) { clearTimeout(timeout); resolve(match[1]); }
      });
      server.stderr.on('data', data => process.stderr.write(data));
    });
    browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
    const page = await browser.newPage({ acceptDownloads: true });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let localModels = ['medgemma-test'];
    const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGZkAAAAASUVORK5CYII=', 'base64');
    const analysisId = 'e'.repeat(32);
    const exported = { analysis_id: analysisId, local_evidence: { schema_version: '1.0', records: [] } };
    await page.route('**/history?**', route => route.fulfill({ json: {
      models: ['medgemma-test'], pagination: { page: 1, total_pages: 1, total: 1, total_all: 1, start: 1, end: 1, counts: { all: 1 } },
      history: [{ id: 'fixture', analysis_id: analysisId, model: 'medgemma-test', verdict: 'INDETERMINADO',
        report: 'Nitidez insuficiente para concluir.', image_url: '/uploads/ui-fixture.png', original_image_url: '/uploads/ui-fixture.png' }],
    } }));
    await page.route('**/agents', route => route.fulfill({ json: {
      development_mode: true, models: ['gemini-flash-latest', 'gemini-2.5-flash'],
      default_model: 'gemini-flash-latest', local_models: localModels, agents: [],
    } }));
    await page.goto(url);
    assert.equal(await page.title(), 'Sato Company | Análise de Integridade');
    assert.equal(await page.getByText('OKTA7', { exact: true }).count(), 0);
    await page.waitForFunction(() => !document.querySelector('#modelSelect').disabled);
    const navigate = async (name) => {
      if (await page.locator('.menu-button').isVisible()) await page.locator('.menu-button').click();
      await page.locator(`[data-page="${name}"]`).click();
    };
    await page.setViewportSize({ width: 1440, height: 950 });
    await page.locator('[data-page="dashboard"]').focus();
    await page.keyboard.press('Enter');
    await page.getByRole('heading', { name: 'Painel', exact: true }).waitFor();
    await page.locator('[data-page="analyze"]').focus();
    await page.keyboard.press('Enter');
    await page.getByRole('heading', { name: 'Analisar imagem', exact: true }).waitFor();
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 950 });
      for (const tab of ['analyze', 'dashboard', 'history', 'settings', 'calibration']) {
        await navigate(tab);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${tab} overflow at ${width}`);
      }
    }
    await navigate('analyze');
    await page.evaluate(() => {
      window.revokedPreviews = [];
      const revoke = URL.revokeObjectURL.bind(URL);
      URL.revokeObjectURL = url => { window.revokedPreviews.push(url); revoke(url); };
    });
    const sampleFile = { name: 'sample.png', mimeType: 'image/png', buffer: image };
    await page.locator('#image').setInputFiles(sampleFile);
    await page.locator('#originalImage').setInputFiles(sampleFile);
    await page.waitForFunction(() => document.querySelector('#preview').naturalWidth > 0);
    for (const width of [1440, 320]) {
      await page.setViewportSize({ width, height: 950 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: `logs/remove-photos-${width}.png`, fullPage: true });
    }
    await page.getByRole('button', { name: 'Remover imagem original', exact: true }).click();
    assert.equal(await page.locator('#originalImage').evaluate(el => el.files.length), 0);
    await page.waitForFunction(() => !document.querySelector('#originalPreview'));
    assert.equal(await page.locator('#image').evaluate(el => el.files.length), 1);
    await page.getByRole('button', { name: 'Remover imagem para análise', exact: true }).click();
    assert.equal(await page.locator('#image').evaluate(el => el.files.length), 0);
    await page.waitForFunction(() => !document.querySelector('#preview') && !document.querySelector('.preview-grid'));
    assert.equal(await page.evaluate(() => window.revokedPreviews.length), 2);
    assert.equal(await page.locator('#image').evaluate(el => el.validity.valueMissing), true);
    await page.locator('#image').setInputFiles(sampleFile);
    await page.getByRole('button', { name: 'Remover imagem para análise', exact: true }).click();
    await navigate('calibration');
    for (const id of ['calibrationImage', 'calibrationOriginal']) {
      await page.locator('#' + id).setInputFiles(sampleFile);
      await page.locator(`[data-remove-photo="${id}"]`).click();
      assert.equal(await page.locator('#' + id).evaluate(el => el.files.length), 0);
      assert.equal(await page.locator(`[data-remove-photo="${id}"]`).isVisible(), false);
    }
    await navigate('history');
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 950 });
      await page.getByRole('button', { name: 'Comparar', exact: true }).click();
      await page.waitForFunction(() => [...document.querySelectorAll('#comparisonDialog img')].every(img => img.complete && img.naturalWidth > 0));
      assert.equal(await page.locator('#comparisonDialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
      await page.locator('#closeComparison').click();
    }
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('link', { name: 'Exportar evidências', exact: true }).click(),
    ]);
    assert.deepEqual(JSON.parse(await fs.readFile(await download.path(), 'utf8')), exported);
    await page.selectOption('#historyModel', 'medgemma-test');
    await navigate('analyze');
    assert.equal(await page.locator('#form #markReal').count(), 0);
    await page.selectOption('#modelSelect', 'lmstudio:medgemma-test');
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#modelSelect').value === 'lmstudio:medgemma-test');
    localModels = [];
    await page.locator('#refreshModels').click();
    await page.waitForFunction(() => document.querySelector('#modelSelect').selectedOptions[0]?.disabled);
    assert.equal(await page.locator('#submit').isDisabled(), true);
    assert.equal(await page.locator('#modelSelect').inputValue(), 'lmstudio:medgemma-test');
    localModels = ['medgemma-test'];
    await page.locator('#refreshModels').click();
    await page.waitForFunction(() => !document.querySelector('#modelSelect').selectedOptions[0]?.disabled);
    let sent = false;
    let submissions = 0;
    await page.route('**/analyze', async route => {
      const body = route.request().postDataBuffer().toString();
      sent = body.includes('medgemma-test') && body.includes('lmstudio');
      assert.equal(body.includes('name="original_image"'), false);
      submissions++;
      assert.equal(route.request().headers().prefer, 'respond-async');
      await route.fulfill({ status: 202, json: { job_id: 'a'.repeat(32) } });
    });
    const completed = { state: 'concluida', result: { schema_version: '2.0', status: 'concluida', experimental: true,
        verdict: 'INDETERMINADO', forensic_quality: 'limitada', audit_status: 'executada',
        forensic_evidence: ['Nitidez limitada.'], structured_result: { justificativa: 'Suporte insuficiente.', limitacoes: [] } } };
    let job = { state: 'executando' };
    let offline = false;
    await page.route('**/jobs/' + 'a'.repeat(32), route => offline ? route.abort('failed') : route.fulfill({ json: job }));
    await page.locator('#image').setInputFiles({ name: 'sample.png', mimeType: 'image/png', buffer: image });
    await page.locator('#submit').click();
    await page.waitForFunction(() => sessionStorage.getItem('perito.activeJob'));
    assert.equal(await page.locator('[data-remove-photo="image"]').isDisabled(), true);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#phase')?.textContent === 'Analisando evidências');
    assert.equal(submissions, 1);
    assert.equal(await page.locator('#submit').isDisabled(), true);
    offline = true;
    await page.locator('#resumeAnalysis').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#submit').isDisabled(), true);
    offline = false;
    job = completed;
    await page.locator('#resumeAnalysis').click();
    await page.waitForFunction(() => document.querySelector('#verdict')?.textContent.includes('Teste experimental'));
    assert.equal(await page.evaluate(() => sessionStorage.getItem('perito.activeJob')), null);
    assert.equal(submissions, 1);
    assert.equal(sent, true);
    job = { state: 'executando' };
    await page.route('**/jobs/' + 'a'.repeat(32) + '/cancel', route => {
      job = { state: 'cancelada' };
      return route.fulfill({ json: job });
    });
    await page.locator('#image').setInputFiles({ name: 'sample.png', mimeType: 'image/png', buffer: image });
    await page.locator('#submit').click();
    await page.locator('#cancelAnalysis').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent === 'Análise cancelada.');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('perito.activeJob')), null);
    const failedHistoryId = 'f'.repeat(32);
    job = { state: 'falhou', result: { schema_version: '2.1', status: 'nao_concluida', conclusion_type: null,
      verdict: null, error: 'Falha de comunicação com Gemini.', history_item: { id: failedHistoryId } } };
    const retryJobId = 'b'.repeat(32);
    await page.route('**/analyses/' + failedHistoryId + '/retry', route => route.fulfill({ status: 202, json: { job_id: retryJobId, state: 'aguardando' } }));
    const impossible = { state: 'concluida', result: { schema_version: '2.1', status: 'concluida',
      conclusion_type: 'impossivel_avaliar', verdict: 'INDETERMINADO', forensic_quality: 'insuficiente',
      audit_status: 'executada', forensic_evidence: ['Resolução insuficiente.'], structured_result: {
        justificativa: 'A qualidade impede uma análise útil.',
        problemas_qualidade: [{ tipo: 'resolucao_insuficiente', descricao: 'A resolução impede observar estruturas úteis.' }],
        limitacoes: ['Não foi possível avaliar a integridade visual.'],
      } } };
    await page.route('**/jobs/' + retryJobId, route => route.fulfill({ json: impossible }));
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#verdict')?.textContent === 'Análise não concluída');
    await page.locator('#retryAnalysis').click();
    await page.waitForFunction(() => document.querySelector('#verdict')?.textContent === 'Impossível de avaliar');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('perito.activeJob')), null);
    assert.deepEqual(errors, []);
    await page.screenshot({ path: 'logs/ui-smoke-mobile.png', fullPage: true });
    console.log('UI: 25 viewport/page checks; comparison, JSON download, model persistence, reconnect, cancellation, failure retry and impossible/inconclusive states passed.');
  } finally {
    if (browser) await browser.close();
    server.stdin.end();
    await serverClosed;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
