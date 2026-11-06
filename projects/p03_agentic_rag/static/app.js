const $ = id => document.getElementById(id);
let busy = false;
let modelReady = false;
let chunks = 0;
async function jsonRequest(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request is invalid. Check its fields and limits.');
  return data;
}
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function controls() {
  $('ask').disabled = busy || !modelReady || !chunks;
  for (const id of ['load-demo', 'add-document', 'model']) $(id).disabled = busy;
}
async function library() {
  const data = await jsonRequest('/api/library');
  chunks = data.chunk_count;
  $('document-count').textContent = data.document_count;
  $('library-status').textContent = `${data.document_count} document(s) · ${chunks} passage(s) stored locally`;
  $('documents').replaceChildren();
  for (const doc of data.documents) {
    const button = document.createElement('button'); button.className = 'document-item'; button.type = 'button';
    button.textContent = doc.title;
    const meta = document.createElement('span'); meta.textContent = `${doc.chunks} passage(s) · ${doc.id}`; button.append(meta);
    button.addEventListener('click', async () => {
      try { const source = await jsonRequest('/api/documents/' + encodeURIComponent(doc.id)); $('source-title').textContent = source.title; $('source-text').textContent = source.text; $('source-view').hidden = false; $('source-view').open = true; }
      catch (error) { status(error.message, true); }
    });
    $('documents').append(button);
  }
  controls();
}
function render(data) {
  $('empty').hidden = true; $('result').hidden = false;
  $('result-title').textContent = data.status === 'answered' ? 'What the library says' : 'The library cannot support an answer';
  $('answer-label').textContent = data.status === 'answered' ? 'SOURCE IDS AND QUOTES CHECKED' : 'NO VERIFIED ANSWER';
  if (data.answer_mode === 'source_quote_fallback') $('answer-label').textContent = 'VERIFIED SOURCE PASSAGE';
  $('asked-question').textContent = data.question;
  $('answer').textContent = data.answer; $('reason').textContent = data.reason;
  $('timing').textContent = `${(data.elapsed_ms / 1000).toFixed(1)}s · ${data.retrieval_attempts} search(es)`;
  $('attempt-count').textContent = data.recovery_used ? 'Recovery search used' : 'No recovery needed';
  $('citations').replaceChildren();
  for (const source of data.citations) {
    const card = document.createElement('article'); card.className = 'citation';
    const title = document.createElement('h3'); title.textContent = source.title;
    const id = document.createElement('div'); id.className = 'id'; id.textContent = source.chunk_id;
    const quote = document.createElement('blockquote'); quote.textContent = source.quote;
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Read the full passage';
    const content = document.createElement('pre'); content.textContent = source.content; details.append(summary, content); card.append(title, id, quote, details); $('citations').append(card);
  }
  $('searches').replaceChildren();
  for (const event of data.trace.filter(event => event.tool === 'retrieve')) {
    const step = document.createElement('div'); step.className = 'search-step';
    const label = document.createElement('strong'); label.textContent = `Search ${event.input.attempt}`;
    const query = document.createElement('p'); query.textContent = event.input.query;
    const sources = document.createElement('p'); sources.textContent = event.result.chunks.map(chunk => chunk.title).join(' · '); step.append(label, query, sources); $('searches').append(step);
  }
  $('trace').textContent = JSON.stringify({model: data.model, embedding_model: data.embedding_model, usage: data.usage, events: data.trace}, null, 2);
}
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { $('question').value = button.dataset.question; $('initial-query').value = ''; $('question').focus(); }));
$('recovery-example').addEventListener('click', () => {
  $('question').value = 'How long do customers have to return unused products?'; $('initial-query').value = 'severity-one paging incident timeline';
  document.querySelector('.advanced').open = true; $('question').focus();
});
$('ask-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !modelReady || !chunks) return;
  const question = $('question').value.trim(); if (!question) return;
  busy = true; controls(); status('Searching and checking source passages. Local answers may take a minute or more.');
  try {
    const data = await jsonRequest('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question, model: $('model').value, initial_query: $('initial-query').value.trim()})});
    render(data); status(data.status === 'answered' ? 'Answer ready. Read the cited passages to check the wording.' : 'No supported answer was produced. You can add a source or refine the question.');
  } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
});
$('load-demo').addEventListener('click', async () => {
  if (busy) return; busy = true; controls(); status('Indexing the fictional sample library on your computer…');
  try { const result = await jsonRequest('/api/library/demo', {method: 'POST'}); await library(); status(`Sample library ready. Added ${result.added_documents} document(s); existing sources were preserved.`); }
  catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
});
$('document-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return; busy = true; controls(); status('Embedding and storing the document locally…');
  try {
    await jsonRequest('/api/documents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: $('document-id').value.trim(), title: $('document-title').value.trim(), text: $('document-text').value.trim()})});
    await library(); $('document-form').reset(); status('Document indexed. You can ask about it now.');
  } catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
});
async function initialize() {
  const results = await Promise.allSettled([library(), jsonRequest('/api/models')]);
  if (results[1].status === 'fulfilled') {
    const models = results[1].value.models;
    $('model').replaceChildren(...models.map(model => new Option(model.name, model.name)));
    if (models.some(model => model.name === 'qwen3:4b')) $('model').value = 'qwen3:4b';
    modelReady = models.length > 0; $('connection').textContent = modelReady ? '● Available on this computer' : 'No chat model is installed.';
  } else { $('connection').textContent = 'Local model service unavailable'; status(results[1].reason.message, true); }
  if (results[0].status === 'rejected') status(results[0].reason.message, true);
  controls();
}
initialize();
