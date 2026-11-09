const $ = id => document.getElementById(id);
const state = {
  mode: 'idle', generation: 0, config: null, context: null, module: null, capture: null,
  controller: null, turnID: null, buffers: [], players: new Set(), queuedUntil: 0,
};

function status(mode, message) {
  state.mode = mode;
  document.body.dataset.mode = mode;
  $('status').textContent = message;
  $('record').disabled = mode !== 'idle' || !state.config?.stt_ready || !state.config?.speech_ready;
  $('send').hidden = mode !== 'recording';
  $('cancel').disabled = mode === 'idle';
  $('replay').disabled = mode !== 'idle' || state.buffers.length === 0;
}

function showError(message = '') {
  $('error').textContent = message;
  $('error').hidden = !message;
}

function time(id, ms) {
  $(id).textContent = ms == null ? '—' : `${(ms / 1000).toFixed(2)} s`;
}

async function audioContext() {
  if (!state.context) state.context = new AudioContext({ sampleRate: state.config.sample_rate });
  await state.context.resume();
  if (state.context.sampleRate !== state.config.sample_rate) throw Error('This browser could not open 16 kHz capture. Try Edge.');
  return state.context;
}

function releaseCapture() {
  const capture = state.capture;
  state.capture = null;
  if (!capture) return;
  clearTimeout(capture.timer);
  if (capture.node) {
    capture.node.port.onmessage = null;
    capture.node.disconnect();
  }
  capture.source?.disconnect();
  capture.stream.getTracks().forEach(track => track.stop());
}

function stopPlayback() {
  for (const source of state.players) {
    source.onended = null;
    source.stop();
    source.disconnect();
  }
  state.players.clear();
  state.queuedUntil = 0;
  document.body.dataset.playback = 'idle';
}

function cancel(message = 'Turn cancelled.') {
  state.generation++;
  const id = state.turnID;
  state.turnID = null;
  state.controller?.abort();
  state.controller = null;
  if (id) fetch(`/api/turn/${id}`, { method: 'DELETE', keepalive: true }).catch(() => {});
  releaseCapture();
  stopPlayback();
  state.buffers = [];
  showError();
  status('idle', message);
}

function schedule(buffer) {
  const context = state.context;
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  const when = Math.max(context.currentTime + 0.02, state.queuedUntil);
  state.queuedUntil = when + buffer.duration;
  state.players.add(source);
  document.body.dataset.playback = 'scheduled';
  source.onended = () => {
    source.disconnect();
    state.players.delete(source);
    if (!state.players.size) {
      document.body.dataset.playback = 'idle';
      if (state.mode === 'playing') status('idle', 'Reply ready.');
    }
  };
  source.start(when);
}

function wav(blocks, frames) {
  const output = new ArrayBuffer(44 + frames * 2);
  const header = new DataView(output);
  const text = (offset, value) => [...value].forEach((char, i) => header.setUint8(offset + i, char.charCodeAt(0)));
  text(0, 'RIFF'); header.setUint32(4, output.byteLength - 8, true); text(8, 'WAVE');
  text(12, 'fmt '); header.setUint32(16, 16, true); header.setUint16(20, 1, true);
  header.setUint16(22, 1, true); header.setUint32(24, state.config.sample_rate, true);
  header.setUint32(28, state.config.sample_rate * 2, true); header.setUint16(32, 2, true);
  header.setUint16(34, 16, true); text(36, 'data'); header.setUint32(40, frames * 2, true);
  let offset = 44;
  for (const block of blocks) {
    for (const sample of block) {
      header.setInt16(offset, sample, true);
      offset += 2;
    }
  }
  return output;
}

async function begin() {
  const generation = ++state.generation;
  showError();
  stopPlayback();
  state.buffers = [];
  $('transcript').textContent = 'Waiting for your question.';
  $('reply').textContent = '';
  for (const id of ['stt-time', 'token-time', 'audio-time', 'total-time']) time(id, null);
  status('requesting', 'Waiting for microphone permission…');
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) throw Error('Open Relay on its local loopback address in a browser with microphone support.');
    const context = await audioContext();
    state.module ||= context.audioWorklet.addModule('/static/capture.js').catch(error => {
      state.module = null;
      throw error;
    });
    await state.module;
    if (generation !== state.generation) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false });
    if (generation !== state.generation) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    const capture = { stream, blocks: [], frames: 0 };
    state.capture = capture;
    capture.source = context.createMediaStreamSource(stream);
    capture.node = new AudioWorkletNode(context, 'relay-capture');
    const max = state.config.sample_rate * state.config.max_seconds;
    capture.node.port.onmessage = ({ data }) => {
      if (state.capture !== capture) return;
      const block = data.subarray(0, max - capture.frames);
      capture.blocks.push(block);
      capture.frames += block.length;
      if (capture.frames >= max) finish();
    };
    capture.source.connect(capture.node).connect(context.destination);
    capture.timer = setTimeout(finish, state.config.max_seconds * 1000);
    status('recording', 'Listening…');
  } catch (error) {
    if (generation !== state.generation) return;
    releaseCapture();
    showError(error.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow access in this browser and try again.'
      : error.name === 'NotFoundError' ? 'No microphone was found. Connect one and try again.' : error.message);
    status('idle', 'Ready to try again.');
  }
}

async function streamResponse(response, generation) {
  if (!response.ok) throw Error((await response.json()).detail || 'Voice request failed.');
  if (!response.body) throw Error('The browser did not receive a voice stream.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let complete = false;
  try {
    while (generation === state.generation) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let end;
      while (generation === state.generation && (end = pending.indexOf('\n')) >= 0) {
        const event = JSON.parse(pending.slice(0, end));
        pending = pending.slice(end + 1);
        if (event.type === 'error') throw Error(event.message);
        if (event.type === 'cancelled') throw Error('The voice turn was cancelled.');
        if (event.type === 'stage') status('processing', event.stage === 'transcribing' ? 'Transcribing locally…' : 'Generating the reply…');
        if (event.type === 'transcript') {
          $('transcript').textContent = event.text;
          time('stt-time', event.elapsed_ms);
        }
        if (event.type === 'delta') {
          $('reply').textContent += event.text;
          time('token-time', event.first_token_ms);
        }
        if (event.type === 'audio') {
          const bytes = Uint8Array.from(atob(event.wav_base64), char => char.charCodeAt(0));
          const buffer = await state.context.decodeAudioData(bytes.buffer);
          if (generation !== state.generation) return;
          state.buffers.push(buffer);
          schedule(buffer);
          if (event.index === 1) time('audio-time', event.elapsed_ms);
        }
        if (event.type === 'done') {
          time('total-time', event.timing.total_ms);
          complete = true;
        }
      }
      if (pending.length > 3_000_000) throw Error('The local voice stream exceeded its response limit.');
    }
    if (generation === state.generation && !complete) throw Error('The voice stream ended before the reply was complete.');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function finish() {
  if (state.mode !== 'recording' || !state.capture) return;
  const generation = state.generation;
  const { frames, blocks } = state.capture;
  releaseCapture();
  if (frames < state.config.sample_rate / 4) {
    showError('Record at least a quarter second of speech.');
    status('idle', 'Ready to try again.');
    return;
  }
  status('processing', 'Sending the local recording…');
  const controller = new AbortController();
  state.controller = controller;
  state.turnID = crypto.randomUUID().replaceAll('-', '');
  try {
    const response = await fetch(`/api/turn/${state.turnID}`, {
      method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav(blocks, frames), signal: controller.signal,
    });
    await streamResponse(response, generation);
    if (generation !== state.generation) return;
    status(state.players.size ? 'playing' : 'idle', state.players.size ? 'Playing the reply…' : 'Reply ready.');
  } catch (error) {
    if (generation !== state.generation) return;
    stopPlayback();
    state.buffers = [];
    showError(error.message);
    status('idle', 'Ready to try again.');
  } finally {
    if (generation === state.generation) {
      state.controller = null;
      state.turnID = null;
    }
  }
}

$('record').addEventListener('click', begin);
$('send').addEventListener('click', finish);
$('cancel').addEventListener('click', () => cancel());
$('replay').addEventListener('click', async () => {
  const generation = state.generation;
  status('playing', 'Playing the reply…');
  try {
    await audioContext();
    if (generation !== state.generation) return;
    state.buffers.forEach(schedule);
  } catch (error) {
    if (generation !== state.generation) return;
    showError(error.message);
    status('idle', 'Reply ready.');
  }
});
window.addEventListener('pagehide', () => cancel());

fetch('/api/config').then(response => response.json()).then(config => {
  state.config = config;
  $('engines').textContent = `${config.stt} · ${config.model} · ${config.speech}`;
  status('idle', config.stt_ready && config.speech_ready ? 'Ready for your question.' : 'Local speech setup is incomplete.');
  if (!config.stt_ready || !config.speech_ready) showError('Run scripts/Setup-Voice.ps1 and check the installed Windows voice.');
}).catch(() => {
  status('idle', 'Local speech setup is unavailable.');
  showError('Start the Relay server and refresh.');
});
