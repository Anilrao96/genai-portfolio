// Uses the installed Edge browser with a fresh, project-local profile.
const { chromium } = require('playwright');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const errors = [];
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime', 'qa-browser'), {
    channel: 'msedge', headless: true, viewport: { width: 1440, height: 1000 },
  });
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8104', { waitUntil: 'networkidle' });
    await page.locator('#send:enabled').waitFor();
    await page.locator('#model').selectOption('qwen2.5:1.5b');
    await page.locator('#prompt').fill('What is 17 + 25? Reply with only the number.');
    await page.locator('#send').click();
    const assistant = page.locator('.message.assistant');
    await assistant.waitFor({ timeout: 150000 });
    const answer = await assistant.locator('div').first().textContent();
    assert.equal(answer.trim(), '42');
    assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(root, 'docs', 'local-ai-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(root, 'docs', 'local-ai-mobile.png'), fullPage: true });
    await page.locator('#clear').click();
    assert.equal(await page.locator('.message').count(), 0);
    const evidence = {
      verified_at: new Date().toISOString(), kind: 'headless_edge_live_ui',
      prompt: 'What is 17 + 25? Reply with only the number.', answer, javascript_errors: errors,
      desktop_screenshot: 'local-ai-desktop.png', mobile_screenshot: 'local-ai-mobile.png',
      mobile_no_horizontal_overflow: true, new_conversation_clears_messages: true,
    };
    await fs.writeFile(path.join(root, 'docs', 'local-ai-browser.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await context.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
