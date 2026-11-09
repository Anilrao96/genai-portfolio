const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const [baseUrl, batchId] = process.argv.slice(2);
  assert.match(baseUrl, /^http:\/\/127\.0\.0\.1:\d+$/);
  assert.match(batchId, /^[0-9a-f]{32}$/);
  const root = path.resolve(__dirname, '..');
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime/p09-browser'), {
    channel: 'msedge', headless: true, viewport: { width: 1440, height: 1040 },
  });
  const errors = [];
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(baseUrl, { waitUntil: 'networkidle' });
    const repaired = page.locator('#history').getByRole('button', { name: new RegExp('^' + batchId.slice(0, 8)) });
    await repaired.click();
    await page.locator('#status').filter({ hasText: 'Batch validated and committed' }).waitFor();
    assert.equal(await page.locator('#orders').textContent(), '4');
    assert.equal(await page.locator('#after').textContent(), '2 / 2');
    assert.equal(await page.locator('#plan tr').count(), 6);
    await page.locator('details summary').click();
    assert.match(await page.locator('#trace').textContent(), /validate_proposal/);
    await page.screenshot({ path: path.join(root, 'docs/docker-agent-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    assert.equal(fits, true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ browser: 'headless Edge', loaded_recreated_container: true,
      persisted_repair_trace_opened: true, orders: 4, valid_repaired_rows: '2 / 2',
      mobile_no_horizontal_overflow: fits, javascript_errors: errors }));
  } finally {
    await context.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
