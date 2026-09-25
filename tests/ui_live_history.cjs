// Read-only browser check against existing local history; no inference or uploads.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {}) });
  try {
    const page = await browser.newPage({ acceptDownloads: true });
    const url = process.env.TEST_URL || 'http://127.0.0.1:9090';
    const records = [];
    let pages = 1;
    for (let number = 1; number <= pages; number++) {
      const response = await page.request.get(`${url}/history?page=${number}`);
      assert.equal(response.ok(), true);
      const payload = await response.json();
      records.push(...payload.history);
      pages = payload.pagination.total_pages;
    }
    let pair;
    let exported;
    let exportData;
    for (const item of records) {
      if (!pair && item.original_image_url && item.image_url) {
        const reference = await page.request.get(url + item.original_image_url);
        const analyzed = await page.request.get(url + item.image_url);
        if (reference.ok() && analyzed.ok()) pair = item;
      }
      if (!exported && item.analysis_id) {
        const response = await page.request.get(`${url}/analysis/${item.analysis_id}/export`);
        if (response.ok()) { exported = item; exportData = await response.json(); }
      }
      if (pair && exported) break;
    }
    assert.ok(pair, 'No existing pair with both images available');
    assert.ok(exported, 'No existing analysis export available');
    // Show only the selected existing records; image and export requests remain real HTTP.
    await page.route('**/history?**', route => route.fulfill({ json: {
      history: pair.id === exported.id ? [pair] : [pair, exported], models: [],
      pagination: { page: 1, total_pages: 1, total: 2, total_all: records.length, start: 1, end: 2, counts: {} },
    } }));
    await page.goto(url);
    await page.locator('[data-page="history"]').click();
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      await page.getByRole('button', { name: 'Comparar', exact: true }).first().click();
      await page.waitForFunction(() => [...document.querySelectorAll('#comparisonDialog img')].every(img => img.complete && img.naturalWidth > 0));
      assert.equal(await page.locator('#comparisonDialog').evaluate(el => el.scrollWidth > el.clientWidth), false);
      await page.screenshot({ path: `logs/live-comparison-${width}.png` });
      await page.locator('#closeComparison').click();
    }
    const downloading = page.waitForEvent('download');
    await page.locator(`a[href="/analysis/${exported.analysis_id}/export"]`).click();
    const download = await downloading;
    assert.deepEqual(JSON.parse(await fs.readFile(await download.path(), 'utf8')), exportData);
    console.log(`Live history: ${records.length} records inspected; existing pair rendered at 1440/390 px; exported JSON matches backend.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
