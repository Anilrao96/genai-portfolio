const {chromium} = require('playwright');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime', 'sql-qa-browser'), {
    channel: 'msedge', headless: true, viewport: {width: 1440, height: 1100},
  });
  const errors = [];
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8107', {waitUntil: 'networkidle'});
    await page.locator('#ask:enabled').waitFor();
    const options = await page.locator('#model option').evaluateAll(items => items.map(item => item.value));
    // The verified evidence selects the available model; do not silently test a different one.
    const live = JSON.parse(await fs.readFile(path.join(root, 'docs', 'sql-assistant-live.json'), 'utf8'));
    assert.ok(options.includes(live.model));
    await page.locator('#model').selectOption(live.model);
    await page.locator('#question').fill('What is the total completed revenue in dollars?');
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/ask') && response.request().method() === 'POST', {timeout: 170000});
    await page.locator('#ask').click();
    const response = await responsePromise;
    const answer = await response.json();
    assert.equal(answer.status, 'answered');
    assert.ok(answer.result.rows.flat().includes(1430));
    await page.locator('#evidence:visible').waitFor();
    assert.match(await page.locator('#result-table').textContent(), /1430/);
    assert.match(await page.locator('#sql').textContent(), /SELECT/i);
    assert.deepEqual(errors, []);
    await page.screenshot({path: path.join(root, 'docs', 'sql-assistant-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({path: path.join(root, 'docs', 'sql-assistant-mobile.png'), fullPage: true});
    async function checkPolicy(question, expectedStatus) {
      await page.locator('#question').fill(question);
      const pending = page.waitForResponse(response => response.url().endsWith('/api/ask') && response.request().method() === 'POST');
      await page.locator('#ask').click();
      const body = await (await pending).json();
      assert.equal(body.status, expectedStatus);
      assert.equal(body.model_call_count, 0);
      await page.locator('#evidence[hidden]').waitFor({state: 'attached'});
      assert.equal(await page.locator('#result-question').textContent(), question);
    }
    await checkPolicy('What is our profit?', 'clarification');
    await checkPolicy('Delete all orders from the database.', 'refused');
    assert.deepEqual(errors, []);
    const evidence = {verified_at: new Date().toISOString(), kind: 'headless_edge_live_sql', model: live.model,
      answer: answer.answer, rows: answer.result.rows, javascript_errors: errors,
      sql_visible: true, table_visible: true, mobile_no_horizontal_overflow: true,
      missing_metric_ui_verified: true, write_refusal_ui_verified: true};
    await fs.writeFile(path.join(root, 'docs', 'sql-assistant-browser.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify(evidence, null, 2));
  } finally { await context.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
