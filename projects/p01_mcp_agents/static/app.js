const $ = id => document.getElementById(id);
const money = cents => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(cents/100);
const reasonLabels = {seat_limit:'Team exceeds plan capacity', '24h_support':'Around-the-clock support unavailable', budget:'Over budget'};
async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check the brief and local service.');
  return data;
}
function element(tag, text, cls) { const node = document.createElement(tag); node.textContent = text; if (cls) node.className=cls; return node; }
function showError(message) { $('error').textContent=message; $('error').hidden=!message; }
function render(data) {
  const run=data.run;
  if(!run){showError(data.error || 'The team could not create a run.');return;}
  $('empty').hidden=true; $('output').hidden=false;
  $('run-label').textContent=`${run.status.toUpperCase().replaceAll('_',' ')} / VERSION ${run.version} / ${run.id.slice(0,8)}`;
  const plan=run.analysis?.recommended_plan;
  $('recommendation').textContent=run.analysis ? (plan ? `${plan[0].toUpperCase()+plan.slice(1)} is the checked choice` : 'No eligible plan fits this brief') : 'Decision is unfinished';
  $('summary').textContent=`${run.requirements.seats} seats · ${money(run.requirements.budget_cents)} budget · ${run.requirements.support_24h ? '24-hour support required' : 'Standard support allowed'} · ${(data.duration_ms/1000).toFixed(1)}s elapsed`;
  $('status').textContent=run.status==='completed' ? 'Decision checked and saved' : run.status==='needs_review' ? 'Reviewer requested attention' : 'Run stopped before completion';
  $('quotes').replaceChildren();
  for(const quote of run.analysis?.quotes || []) {const row=document.createElement('tr');row.append(element('td',quote.plan_id),element('td',money(quote.monthly_cents)),element('td',quote.eligible ? 'All met' : quote.reasons.map(reason => reasonLabels[reason] || reason).join(', '), quote.eligible ? 'pass':'fail'));$('quotes').append(row);}
  $('handoffs').replaceChildren();
  for(const [role,key] of [['researcher','research'],['analyst','analysis'],['reviewer','review']]) if(run[key]) {const node=element('div','','handoff');node.append(element('b',`${role} → v${{research:1,analysis:2,review:3}[key]}${run[key].note_source==='tool_fallback' ? ' · tool fallback' : ' · model note'}`),element('p',run[key].note));$('handoffs').append(node);}
  $('counts').textContent=`${data.counts?.model_calls || 0} model / ${data.counts?.tool_calls || 0} tool calls`;
  $('trace').replaceChildren();
  for(const event of data.trace || []) {const node=element('div','','trace-event');node.append(element('b',`${event.role} · ${event.kind}${event.name ? ' / '+event.name : ''}`));node.append(element('pre',JSON.stringify(event,null,2)));$('trace').append(node);}
  showError(data.error || '');
}
async function history(){ const data=await request('/api/runs');$('history').replaceChildren();if(!data.runs.length)$('history').textContent='No saved decisions yet.';for(const run of data.runs){const button=element('button',`${run.id.slice(0,8)} · ${run.status.replaceAll('_',' ')} · ${run.requirements.seats} seats`);button.type='button';button.addEventListener('click',async()=>{try{render(await request('/api/runs/'+run.id));}catch(error){showError(error.message);}});$('history').append(button);} }
$('decision-form').addEventListener('submit', async event => {event.preventDefault();showError('');$('submit').disabled=true;document.body.classList.add('busy');$('status').textContent='Council in session · researching, analyzing and reviewing…';try{const data=await request('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seats:Number($('seats').value),budget_cents:Math.round(Number($('budget').value)*100),support_24h:$('support').checked,goal:$('goal').value,model:$('model').value})});render(data);await history();}catch(error){showError(error.message);$('status').textContent='Could not complete this run';}finally{$('submit').disabled=false;document.body.classList.remove('busy');}});
(async()=>{try{const [models,catalog]=await Promise.all([request('/api/models'),request('/api/catalog')]);$('model').replaceChildren();for(const model of models.models){const option=element('option',model.name);option.value=model.name;option.selected=model.name===catalog.default_model;$('model').append(option);}if(!models.models.length)throw new Error('No chat models installed. Start the project Ollama instance and pull qwen3:4b.');for(const plan of catalog.plans){const node=document.createElement('div');node.append(element('b',plan.name),element('span',`${money(plan.seat_cents)}/seat + ${money(plan.base_cents)} base`));$('catalog').append(node);}await history();}catch(error){showError(error.message);$('submit').disabled=true;}})();
