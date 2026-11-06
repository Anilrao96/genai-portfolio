const $ = id => document.getElementById(id);
let history = [];
let busy = false;
let ready = false;

function setStatus(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function renderMessage(role, text, metrics) {
  $('welcome')?.remove();
  const article = document.createElement('article');
  article.className = 'message ' + role;
  const label = document.createElement('span');
  label.className = 'role';
  label.textContent = role === 'user' ? 'YOU' : 'LOCAL ASSISTANT';
  const body = document.createElement('div');
  body.textContent = text;
  article.append(label, body);
  if (metrics) {
    const meta = document.createElement('div');
    meta.className = 'metrics';
    meta.textContent = `${(metrics.elapsed_ms / 1000).toFixed(1)}s · ${metrics.output_tokens ?? '?'} output tokens · ${metrics.model}`;
    article.append(meta);
  }
  $('messages').append(article);
  article.scrollIntoView({ block: 'end' });
  return article;
}
async function jsonRequest(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'The conversation is too long or invalid. Start a new conversation.';
    throw new Error(detail);
  }
  return data;
}
async function loadModels() {
  $('refresh').disabled = true;
  ready = false;
  $('send').disabled = true;
  try {
    const data = await jsonRequest('/api/models');
    $('model').replaceChildren();
    for (const model of data.models) {
      const option = document.createElement('option');
      option.value = model.name;
      option.textContent = model.name;
      $('model').append(option);
    }
    if (data.models.some(model => model.name === 'qwen2.5:1.5b')) $('model').value = 'qwen2.5:1.5b';
    ready = data.models.length > 0;
    $('connection').textContent = ready ? `${data.models.length} model(s) available locally` : 'No models yet. Pull a model using the README instructions.';
  } catch (error) {
    $('model').replaceChildren(new Option('Ollama unavailable', ''));
    $('connection').textContent = error.message;
  } finally {
    $('refresh').disabled = false;
    $('send').disabled = busy || !ready;
  }
}
$('refresh').addEventListener('click', loadModels);
$('clear').addEventListener('click', () => { history = []; $('messages').replaceChildren(); setStatus('New conversation. Nothing is saved on the server.'); });
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => { $('prompt').value = button.dataset.prompt; $('prompt').focus(); }));
$('chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = $('prompt').value.trim();
  if (!prompt || busy || !ready) return;
  if (history.length >= 20 || history.reduce((n, m) => n + m.content.length, 0) + prompt.length > 12000) {
    setStatus('Conversation limit reached. Start a new conversation.', true); return;
  }
  busy = true;
  for (const id of ['send', 'clear', 'refresh', 'model']) $(id).disabled = true;
  const pendingMessage = renderMessage('user', prompt);
  const messages = [...history, { role: 'user', content: prompt }];
  $('prompt').value = '';
  setStatus('Generating on your computer… The first response may take longer while the model loads.');
  try {
    const result = await jsonRequest('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: $('model').value, messages }) });
    renderMessage('assistant', result.answer, result);
    history = [...messages, { role: 'assistant', content: result.answer }];
    setStatus('Responses can be inaccurate. Check facts and code before using them.');
  } catch (error) {
    pendingMessage.remove();
    setStatus(error.message, true);
    $('prompt').value = prompt;
  } finally {
    busy = false;
    for (const id of ['clear', 'refresh', 'model']) $(id).disabled = false;
    $('send').disabled = !ready;
    $('prompt').focus();
  }
});
loadModels();
