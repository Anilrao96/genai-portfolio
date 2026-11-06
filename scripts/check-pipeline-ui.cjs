const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const evidence=JSON.parse(await fs.readFile(path.join(root,'docs/pipeline-live.json'),'utf8'));
  assert.equal(evidence.complete,true);assert.equal(evidence.passed,true);
  const context=await chromium.launchPersistentContext(path.join(root,'.runtime/pipeline-qa-browser'),{
    channel:'msedge',headless:true,viewport:{width:1440,height:1100},
  });
  const errors=[];
  try{
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:8105',{waitUntil:'networkidle'});
    await page.locator('#model option[value="qwen3:4b"]').waitFor({state:'attached'});
    const choices=await page.locator('#model option').evaluateAll(options=>options.map(option=>option.value));
    assert.ok(!choices.some(choice=>choice.startsWith('nomic-embed')));
    const variant=Number(process.argv[2] || 1);
    assert.ok(Number.isInteger(variant)&&variant>=0&&variant<729,'Use a fresh header variant from 0 to 728.');
    const config=await (await page.request.get('http://127.0.0.1:8105/api/config')).json();
    let remaining=variant;
    const headers=Object.keys(config.aliases).map(target=>{const alias=config.aliases[target][remaining%3];remaining=Math.floor(remaining/3);return alias;});
    const ids=[6000+variant*2,6001+variant*2].map(id=>'ORD-'+id);
    const source=headers.join(',')+'\n'+ids[0]+',Cedar Studio,3.0,$19.95,usd,11/03/2026\n'+ids[1]+',Dune Systems,2.0,"$1,200.00",usd,11/04/2026\n';
    await page.locator('#source').fill(source);await page.locator('#date-style').selectOption('month_first');
    await page.locator('#model').selectOption('qwen3:4b');
    const pending=page.waitForResponse(response=>response.url().endsWith('/api/ingest')&&response.request().method()==='POST',{timeout:200000});
    await page.locator('#ingest').click();const result=await (await pending).json();
    assert.equal(result.status,'committed');assert.equal(result.plan_origin,'model');assert.ok(result.model_calls_this_request>=1);
    await page.locator('#status').filter({hasText:'Batch validated and committed'}).waitFor();
    assert.equal(await page.locator('#after').textContent(),'2 / 2');assert.equal(await page.locator('#plan tr').count(),6);
    await page.locator('details summary').click();assert.match(await page.locator('#trace').textContent(),/validate_proposal/);await page.locator('details summary').click();
    const failed=evidence.cases.find(item=>item.id==='invalid_value_quarantined').response.batch_id;
    const failedRow=page.locator('#history .batch').filter({hasText:failed.slice(0,8)});
    await failedRow.getByRole('button',{name:'Correct & replay',exact:true}).click();
    await page.locator('#replay-label').waitFor({state:'visible'});
    assert.match(await page.locator('#source').inputValue(),/,0\.0,/);assert.equal(await page.locator('#replay-label').isVisible(),true);
    await page.locator('#cancel-replay').click();await page.locator('#source').fill(source);
    const state=await (await page.request.get('http://127.0.0.1:8105/api/snapshot')).json();
    const baseline=evidence.cases.find(item=>item.id==='standard_batch').response.committed_revision;
    for(const target of [baseline,state.active_revision]){
      await page.locator('#rollback-target').selectOption(String(target));
      const rollback=page.waitForResponse(response=>response.url().endsWith('/api/rollback')&&response.request().method()==='POST');
      await page.locator('#rollback').click();assert.equal((await rollback).status(),200);
      await page.locator('#revision').filter({hasText:new RegExp('^'+target+'$')}).waitFor();
    }
    await page.locator('#history .batch').filter({hasText:result.batch_id.slice(0,8)}).getByRole('button').first().click();
    await page.locator('#status').filter({hasText:'Batch validated and committed'}).waitFor();
    assert.ok((await page.locator('#records').textContent()).includes(ids[0]));
    await page.screenshot({path:path.join(root,'docs/pipeline-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
    assert.equal(noOverflow,true);await page.screenshot({path:path.join(root,'docs/pipeline-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
    const output={verified_at:new Date().toISOString(),mode:'actual headless Edge model-backed repair',model:'qwen3:4b',
      batch_id:result.batch_id,plan_origin:result.plan_origin,model_calls:result.model_calls_this_request,duration_ms:result.duration_ms,
      header_variant:variant,source_order_ids:ids,
      quality_before:result.before,quality_after:result.after,trace_opened:true,quarantine_replay_editor_verified:true,
      snapshot_restore_and_return_verified:true,embedding_model_excluded:true,javascript_errors:errors,mobile_no_horizontal_overflow:noOverflow};
    await fs.writeFile(path.join(root,'docs/pipeline-browser.json'),JSON.stringify(output,null,2)+'\n');
    console.log(JSON.stringify({status:result.status,model_calls:result.model_calls_this_request,duration_ms:result.duration_ms,javascript_errors:errors,mobile_no_horizontal_overflow:noOverflow},null,2));
  }finally{await context.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
