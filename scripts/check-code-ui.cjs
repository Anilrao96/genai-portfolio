const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const context=await chromium.launchPersistentContext(path.join(root,'.runtime/code-qa-browser'),{
    channel:'msedge',headless:true,viewport:{width:1440,height:1100},
  });
  const errors=[];
  try{
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:8106',{waitUntil:'networkidle'});
    await page.locator('#model option[value="qwen3:4b"]').waitFor({state:'attached'});
    assert.match(await page.locator('#runtime').textContent(),/VERIFIED/);
    const choices=await page.locator('#model option').evaluateAll(items=>items.map(item=>item.value));
    assert.ok(!choices.some(choice=>choice.startsWith('nomic-embed')));
    await page.locator('#blank').click();assert.equal(await page.locator('#code').inputValue(),'');
    await page.locator('#starter').click();assert.match(await page.locator('#code').inputValue(),/sum\(data\) \/ len\(data\)/);
    await page.locator('#model').selectOption('qwen3:4b');
    const response=page.waitForResponse(item=>item.url().endsWith('/api/run')&&item.request().method()==='POST',{timeout:260000});
    await page.locator('#run').click();const result=await (await response).json();
    assert.equal(result.status,'passed');assert.ok(result.executions>=2);assert.ok(result.model_calls>=1);
    assert.match(result.attempts[0].feedback,/ZeroDivisionError/);
    assert.equal(result.attempts.at(-1).tests_passed,4);
    await page.locator('#status').filter({hasText:'Every authored case passed'}).waitFor();
    assert.equal(await page.locator('.attempt').count(),result.executions);
    await page.getByText('Inspect workflow and isolation trace',{exact:true}).click();const trace=await page.locator('#trace').textContent();
    assert.match(trace,/"network": "none"/);assert.match(trace,/"no_new_privileges": true/);
    await page.getByText('Inspect workflow and isolation trace',{exact:true}).click();
    await page.reload({waitUntil:'networkidle'});
    await page.locator('#history button').filter({hasText:result.id.slice(0,8)}).click();
    await page.locator('#status').filter({hasText:'Every authored case passed'}).waitFor();
    assert.match(await page.locator('#run-label').textContent(),new RegExp(result.id.slice(0,8)));
    await page.screenshot({path:path.join(root,'docs/code-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
    assert.equal(noOverflow,true);await page.screenshot({path:path.join(root,'docs/code-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    const evidence={verified_at:new Date().toISOString(),mode:'actual headless Edge → FastAPI → LangGraph → local Qwen3 → native WSL OCI containers',
      run_id:result.id,status:result.status,model:result.model,model_calls:result.model_calls,executions:result.executions,
      duration_ms:result.duration_ms,first_feedback:result.attempts[0].feedback,last_tests_passed:result.attempts.at(-1).tests_passed,
      attempt_history_visible:true,trace_opened:true,persisted_run_reload_verified:true,embedding_model_excluded:true,
      javascript_errors:errors,mobile_no_horizontal_overflow:noOverflow};
    await fs.writeFile(path.join(root,'docs/code-browser.json'),JSON.stringify(evidence,null,2)+'\n');
    console.log(JSON.stringify(evidence,null,2));
  }finally{await context.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
