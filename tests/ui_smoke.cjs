const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { spawn } = require('node:child_process');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const server = spawn(process.env.TEST_PYTHON || 'python', ['-u', path.join(__dirname, 'ui_server.py')], { windowsHide: true });
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
    await page.waitForFunction(() => !document.querySelector('#modelSelect').disabled);
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 950 });
      for (const tab of ['analyze', 'dashboard', 'history', 'settings', 'calibration']) {
        await page.locator(`[data-page="${tab}"]`).click();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${tab} overflow at ${width}`);
      }
    }
    await page.locator('[data-page="history"]').click();
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 950 });
      await page.getByRole('button', { name: 'Comparar', exact: true }).click();
      await page.waitForFunction(() => [...document.querySelectorAll('#comparisonDialog img')].every(img => img.complete && img.naturalWidth > 0));
      assert.equal(await page.locator('#comparisonDialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
      await page.locator('#closeComparison').click();
    }
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Exportar evidencias' }).click();
    const download = await downloadPromise;
    assert.deepEqual(JSON.parse(await fs.readFile(await download.path(), 'utf8')), exported);
    await page.selectOption('#historyModel', 'medgemma-test');
    await page.locator('[data-page="analyze"]').click();
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
    await page.waitForFunction(() => !document.querySelector('#submit').disabled);
    let sent = false;
    let submissions = 0;
    await page.route('**/analyze', async route => {
      const body = route.request().postDataBuffer().toString();
      sent = body.includes('medgemma-test') && body.includes('lmstudio');
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
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#status').textContent === 'Analisando');
    assert.equal(submissions, 1);
    assert.equal(await page.locator('#submit').isDisabled(), true);
    offline = true;
    await page.locator('#resumeAnalysis').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#submit').isDisabled(), true);
    offline = false;
    job = completed;
    await page.locator('#resumeAnalysis').click();
    await page.waitForFunction(() => document.querySelector('#verdict').textContent.includes('Teste local'));
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
    await page.waitForFunction(() => document.querySelector('#status').textContent === 'Analise cancelada.');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('perito.activeJob')), null);
    assert.deepEqual(errors, []);
    await page.screenshot({ path: 'logs/ui-smoke-mobile.png', fullPage: true });
    console.log('UI: 25 viewport/page checks; comparison, JSON download, model persistence/unavailability, reload/reconnect without resubmission, cancellation and calibration separation passed.');
  } finally {
    if (browser) await browser.close();
    server.stdin.end();
    await serverClosed;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
