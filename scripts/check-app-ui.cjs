const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const builderOrigin = 'http://127.0.0.1:8108';
const previewOrigin = 'http://127.0.0.1:8118';

async function main() {
  const capture = JSON.parse(await fs.readFile(path.join(root, 'docs/app-builder-core-live.json'), 'utf8'));
  assert.equal(capture.run.status, 'passed', 'Run probe-app-core.py successfully first.');
  const run = capture.run;
  const browser = await chromium.launchPersistentContext(path.join(root, '.runtime/app-builder-browser'), {
    channel: 'msedge', headless: true, viewport: { width: 1440, height: 1080 }
  });
  const blocked = [];
  const errors = [];
  const requests = [];
  try {
    await browser.route('**/*', route => {
      const url = new URL(route.request().url());
      if ([builderOrigin, previewOrigin].includes(url.origin)) return route.continue();
      blocked.push(url.origin);
      return route.abort();
    });
    const page = await browser.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.url().startsWith(`${previewOrigin}/r/${run.id}/api/items`)) {
        requests.push({ method: response.request().method(), status: response.status() });
      }
    });
    const api = (method, expectedStatus) => page.waitForResponse(response =>
      response.url().startsWith(`${previewOrigin}/r/${run.id}/api/items`) &&
      response.request().method() === method && response.status() === expectedStatus, { timeout: 45000 });
    const loadBuild = async () => {
      await page.getByRole('button', { name: new RegExp(run.id.slice(0, 8)) }).click();
      await page.locator('#status').filter({ hasText: 'Built, reviewed, ready to try.' }).waitFor();
      await page.frameLocator('#preview').getByRole('textbox').waitFor();
    };
    await page.goto(builderOrigin, { waitUntil: 'networkidle' });
    assert.match(await page.locator('#runtime').textContent(), /VERIFIED/);
    const options = await page.locator('#model option').evaluateAll(items => items.map(item => item.value));
    assert.ok(options.includes(run.model));
    assert.ok(!options.some(name => name.startsWith('nomic-embed')));
    const initial = api('GET', 200);
    await loadBuild();
    await initial;
    await page.locator('#trace-details summary').click();
    assert.match(await page.locator('#trace').textContent(), /qa_scenarios/);
    await page.locator('#trace-details summary').click();
    const frame = page.frameLocator('#preview');
    const resetGet = api('GET', 200);
    await frame.getByRole('button', { name: 'Reset preview' }).click();
    assert.deepEqual(await (await resetGet).json(), []);

    async function add(title) {
      await frame.getByRole('textbox').fill(title);
      const result = api('POST', 201);
      await frame.locator('form').getByRole('button', { name: /^Add\b/i }).click();
      const record = await (await result).json();
      assert.equal(record.title, title);
      assert.equal(record.done, false);
      await frame.locator('li').filter({ hasText: title }).waitFor();
      return record;
    }
    const book = await add('The Cedar Atlas');
    const toggle = api('PATCH', 200);
    await frame.locator('li').filter({ hasText: book.title }).getByRole('checkbox').click();
    assert.equal((await (await toggle).json()).done, true);
    await frame.locator('li').filter({ hasText: book.title }).locator('input:checked').waitFor();
    const removed = await add('A Map of Quiet Rivers');
    const deletion = api('DELETE', 204);
    await frame.locator('li').filter({ hasText: removed.title }).getByRole('button', { name: /^(Delete|Remove)\b/i }).click();
    await deletion;
    await frame.locator('li').filter({ hasText: removed.title }).waitFor({ state: 'hidden' });

    await page.reload({ waitUntil: 'networkidle' });
    const persisted = api('GET', 200);
    await loadBuild();
    assert.deepEqual(await (await persisted).json(), [{ ...book, done: true }]);
    await page.frameLocator('#preview').locator('li').filter({ hasText: book.title }).locator('input:checked').waitFor();
    await page.locator('#preview').scrollIntoViewIfNeeded();
    await page.locator('#preview').screenshot({ path: path.join(root, 'docs/app-builder-preview.png') });
    await page.screenshot({ path: path.join(root, 'docs/app-builder-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const previewFrame = page.frames().find(child => child.url().startsWith(previewOrigin));
    assert.equal(await previewFrame.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#preview').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(root, 'docs/app-builder-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    const journal = JSON.parse(await fs.readFile(path.join(root, '.runtime/app-builder-qa/workspaces', run.id, 'preview-journal.json'), 'utf8'));
    const evidence = {
      captured_at: new Date().toISOString(), run_id: run.id, title: run.spec.title,
      mode: 'actual Edge generated React and isolated FastAPI preview using saved live model build',
      fresh_model_calls: 0, passed: true, requests, replayed_requests: journal.requests.length,
      container_execution_ms: journal.durations_ms, final_items: journal.responses.at(-1).body,
      reset_verified: true, state_and_build_survived_reload: true, model_choices_exclude_embeddings: true,
      no_horizontal_overflow_at_390: true, javascript_errors: errors, external_requests: blocked
    };
    await fs.writeFile(path.join(root, 'docs/app-builder-browser.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
