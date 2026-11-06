const {chromium} = require('playwright');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const context = await chromium.launchPersistentContext(path.join(root, '.runtime', 'mcp-qa-browser'), {
    channel: 'msedge', headless: true, viewport: {width: 1440, height: 1100},
  });
  const errors = [];
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8101', {waitUntil:'networkidle'});
    await page.locator('#submit:enabled').waitFor();
    const choices = await page.locator('#model option').evaluateAll(items => items.map(item => item.value));
    assert.ok(!choices.some(choice => choice.startsWith('nomic-embed')));
    await page.locator('#model').selectOption('qwen3:4b');
    const pending = page.waitForResponse(response => response.url().endsWith('/api/decide') && response.request().method()==='POST', {timeout:270000});
    await page.locator('#submit').click();
    const result = await (await pending).json();
    assert.equal(result.error, null);
    assert.equal(result.run.status,'completed');
    assert.equal(result.run.analysis.recommended_plan,'team');
    await page.locator('#status').filter({hasText:'Decision checked and saved'}).waitFor();
    assert.match(await page.locator('#quotes').textContent(), /236\.00/);
    assert.equal(await page.locator('.handoff').count(),3);
    await page.locator('details summary').click();
    assert.ok(await page.locator('.trace-event').count() >= 20);
    assert.match(await page.locator('#trace').textContent(), /protocol_version/);
    await page.locator('details summary').click();
    await page.reload({waitUntil:'networkidle'});
    await page.locator('#history button').first().click();
    await page.locator('#status').filter({hasText:'Decision checked and saved'}).waitFor();
    assert.match(await page.locator('#run-label').textContent(),new RegExp(result.run.id.slice(0,8)));
    await page.screenshot({path:path.join(root,'docs','mcp-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
    assert.equal(noOverflow,true);
    await page.screenshot({path:path.join(root,'docs','mcp-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const evidence = {verified_at:new Date().toISOString(),mode:'actual headless Edge model request',model:'qwen3:4b',
      run_id:result.run.id,status:result.run.status,recommended_plan:result.run.analysis.recommended_plan,
      duration_ms:result.duration_ms,counts:result.counts,javascript_errors:errors,
      trace_opened:true,history_survived_reload:true,embedding_model_excluded:true,mobile_no_horizontal_overflow:noOverflow};
    await fs.writeFile(path.join(root,'docs','mcp-browser.json'),JSON.stringify(evidence,null,2)+'\n');
    console.log(JSON.stringify(evidence,null,2));
  } finally {await context.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
