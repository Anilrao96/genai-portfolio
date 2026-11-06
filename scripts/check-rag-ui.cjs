const {chromium} = require('playwright');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime', 'rag-qa-browser'), {
    channel: 'msedge', headless: true, viewport: {width: 1440, height: 1100},
  });
  const errors = [];
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8103', {waitUntil: 'networkidle'});
    await page.locator('#ask:enabled').waitFor();
    const live = JSON.parse(await fs.readFile(path.join(root, 'docs', 'rag-live.json'), 'utf8'));
    assert.equal(live.passed, true);
    const choices = await page.locator('#model option').evaluateAll(items => items.map(item => item.value));
    assert.ok(!choices.some(choice => choice.startsWith('nomic-embed')));
    await page.locator('#model').selectOption(live.model);
    await page.locator('#question').fill('How long do customers have to return unused products?');
    const pending = page.waitForResponse(response => response.url().endsWith('/api/ask') && response.request().method() === 'POST', {timeout: 270000});
    await page.locator('#ask').click();
    const result = await (await pending).json();
    assert.equal(result.status, 'answered');
    assert.ok(result.citations.some(citation => citation.document_id === 'returns-policy' && citation.quote.includes('30')));
    await page.locator('.citation').first().waitFor();
    assert.match(await page.locator('#answer').textContent(), /30/);
    assert.deepEqual(errors, []);
    await page.screenshot({path: path.join(root, 'docs', 'rag-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({path: path.join(root, 'docs', 'rag-mobile.png'), fullPage: true});
    await page.locator('.document-item').filter({hasText: 'Returns and refunds'}).click();
    await page.locator('#source-view:not([hidden])').waitFor();
    assert.match(await page.locator('#source-text').textContent(), /30 calendar days/);
    const evidence = {verified_at: new Date().toISOString(), kind: 'headless_edge_live_rag', model: live.model,
      answer: result.answer, citations: result.citations, javascript_errors: errors,
      elapsed_ms: result.elapsed_ms, answer_mode: result.answer_mode,
      source_view_verified: true, embedding_model_excluded_from_chat_choices: true,
      mobile_no_horizontal_overflow: true};
    await fs.writeFile(path.join(root, 'docs', 'rag-browser.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify({verified_at: evidence.verified_at, cited_documents: result.citations.map(citation => citation.document_id),
      javascript_errors: errors, source_view_verified: true, mobile_no_horizontal_overflow: true}, null, 2));
  } finally { await context.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
