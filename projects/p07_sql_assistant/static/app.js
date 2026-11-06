const $ = id => document.getElementById(id);
let busy = false;
let ready = false;

async function jsonRequest(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || 'The request is invalid. Check its size and fields.');
  }
  return body;
}
function status(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}
function renderResult(data) {
  $('empty').hidden = true;
  $('result').hidden = false;
  $('result-title').textContent = ({answered: 'The answer', clarification: 'A little more context', refused: 'This request cannot run', failed: 'The query could not finish'})[data.status];
  $('result-question').textContent = data.question;
  $('answer-label').textContent = data.summary_source === 'model' ? 'AI SUMMARY · CHECK AGAINST THE ROWS' : 'REQUEST OUTCOME';
  $('answer').textContent = data.answer;
  $('timing').textContent = `${(data.elapsed_ms / 1000).toFixed(1)}s · ${data.model}`;
  $('trace').textContent = JSON.stringify({usage: data.usage, events: data.trace}, null, 2);
  $('evidence').hidden = !data.result;
  $('result-note').textContent = '';
  if (!data.result) return;
  const result = data.result;
  $('row-count').textContent = `${result.row_count} row(s)${result.truncated ? ' · partial results' : ''} · ${result.query_ms} ms SQL`;
  $('sql').textContent = data.sql;
  $('result-note').textContent = result.truncated || result.cell_values_truncated ? 'Some rows or long values were limited. This may be a partial result.' : 'The table below contains the actual query result.';
  const head = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const column of result.columns) {
    const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = column; headerRow.append(cell);
  }
  head.append(headerRow);
  const body = document.createElement('tbody');
  for (const row of result.rows) {
    const tr = document.createElement('tr');
    for (const value of row) { const td = document.createElement('td'); td.textContent = value === null ? 'NULL' : String(value); tr.append(td); }
    body.append(tr);
  }
  $('result-table').replaceChildren(head, body);
}
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  $('question').value = button.dataset.question;
  $('question').focus();
}));
$('ask-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (busy || !ready || !question) return;
  busy = true;
  for (const id of ['ask', 'model', 'row-limit']) $(id).disabled = true;
  status('Writing a read-only query, checking it, then explaining the result…');
  try {
    const data = await jsonRequest('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question, model: $('model').value, row_limit: Number($('row-limit').value)})});
    renderResult(data);
    status(data.status === 'answered' ? 'Query complete. Inspect the SQL and results below.' : 'No data was changed. You can refine your question.');
  } catch (error) { status(error.message, true); }
  finally {
    busy = false;
    for (const id of ['model', 'row-limit']) $(id).disabled = false;
    $('ask').disabled = !ready;
  }
});
async function initialize() {
  try {
    const [catalog, models] = await Promise.all([jsonRequest('/api/catalog'), jsonRequest('/api/models')]);
    $('schema').textContent = catalog.schema + '\n' + catalog.definitions;
    $('tables').replaceChildren();
    for (const table of catalog.tables) {
      const div = document.createElement('div'); div.className = 'table-item';
      const name = document.createElement('span'); name.textContent = '▦ ' + table.name;
      const count = document.createElement('span'); count.textContent = table.row_count + ' rows'; div.append(name, count); $('tables').append(div);
    }
    $('model').replaceChildren();
    for (const model of models.models) $('model').append(new Option(model.name, model.name));
    if (models.models.some(model => model.name === catalog.default_model)) $('model').value = catalog.default_model;
    ready = models.models.length > 0;
    $('connection').textContent = ready ? '● Available on this computer' : 'No local models. See the setup instructions.';
    $('ask').disabled = !ready;
    status(ready ? 'Ready. Choose a sample question or write your own.' : 'Pull a model on the portfolio Ollama instance, then refresh this page.');
  } catch (error) { $('connection').textContent = 'Local model unavailable'; status(error.message, true); }
}
initialize();
