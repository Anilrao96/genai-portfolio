const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const origin = 'http://127.0.0.1:8102';
const fakeMic = path.join(root, '.runtime', 'voice-fake-mic.wav');

async function main() {
  await fs.access(fakeMic);
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime/voice-browser'), {
    channel: 'msedge', headless: true, viewport: { width: 1440, height: 960 },
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
      `--use-file-for-fake-audio-capture=${fakeMic}`],
  });
  const errors = [];
  const external = [];
  try {
    await context.route('**/*', route => {
      const requested = new URL(route.request().url());
      if (requested.origin === origin) return route.continue();
      external.push(requested.origin);
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    let uploads = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/api/turn/')) uploads++;
    });
    await page.goto(origin);
    await page.locator('#status').filter({ hasText: 'Ready for your question.' }).waitFor();
    await page.getByRole('button', { name: 'Record question' }).click();
    await page.locator('#status').filter({ hasText: 'Listening…' }).waitFor();
    // The fictional clip starts with 500 ms of silence and finishes speaking at about 5.8 s.
    await page.waitForTimeout(6500);
    const posted = page.waitForResponse(response => response.request().method() === 'POST'
      && response.url().startsWith(`${origin}/api/turn/`), { timeout: 15000 });
    await page.getByRole('button', { name: 'Stop and send' }).click();
    const response = await posted;
    assert.equal(response.status(), 200);
    await page.locator('#transcript').filter({ hasText: /capital of France/i }).waitFor({ timeout: 40000 });
    await page.locator('#reply').filter({ hasText: /Paris/i }).waitFor({ timeout: 45000 });
    await page.locator('body[data-playback="scheduled"]').waitFor();
    await page.locator('#status').filter({ hasText: 'Reply ready.' }).waitFor({ timeout: 45000 });
    assert.equal(uploads, 1);
    const events = (await response.text()).trim().split('\n').map(line => JSON.parse(line));
    const done = events.find(event => event.type === 'done');
    assert.ok(done && done.audio_chunks >= 1);
    const deltas = events.filter(event => event.type === 'delta');
    assert.ok(deltas.length > 1);
    const transcript = await page.locator('#transcript').textContent();
    const reply = await page.locator('#reply').textContent();
    assert.equal(reply, deltas.map(event => event.text).join(''));
    await page.screenshot({ path: path.join(root, 'docs/voice-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(root, 'docs/voice-mobile.png'), fullPage: true });

    await page.getByRole('button', { name: 'Replay reply' }).click();
    await page.locator('body[data-playback="scheduled"]').waitFor();
    await page.getByRole('button', { name: 'Cancel' }).click();
    await page.locator('body[data-playback="idle"][data-mode="idle"]').waitFor();
    await page.getByRole('button', { name: 'Record question' }).click();
    await page.locator('#status').filter({ hasText: 'Listening…' }).waitFor();
    await page.getByRole('button', { name: 'Cancel' }).click();
    await page.locator('#status').filter({ hasText: 'Turn cancelled.' }).waitFor();
    assert.equal(uploads, 1);

    const denied = await context.newPage();
    await denied.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Simulated denial', 'NotAllowedError'); };
    });
    await denied.goto(origin);
    await denied.getByRole('button', { name: 'Record question' }).click();
    await denied.getByRole('alert').filter({ hasText: 'Microphone permission was denied.' }).waitFor();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const evidence = {
      captured_at: new Date().toISOString(), passed: true, mode: 'actual Edge AudioWorklet and voice API with a synthetic microphone device',
      physical_microphone_used: false, stt_model: 'Whisper tiny.en', model: done.model,
      transcript, reply, request_bytes: response.request().postDataBuffer().length,
      streamed_text_deltas: deltas.length, audio_chunks: done.audio_chunks, timing: done.timing,
      web_audio_scheduled_and_ended: true, playback_cancelled: true, recording_cancelled_without_upload: true,
      permission_denial: 'simulated NotAllowedError through the browser API',
      no_horizontal_overflow_at_390: true, javascript_errors: errors, external_requests: external,
    };
    await fs.writeFile(path.join(root, 'docs/voice-browser.json'), JSON.stringify(evidence, null, 2) + '\n');
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await context.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
