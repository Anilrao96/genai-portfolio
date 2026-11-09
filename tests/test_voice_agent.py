"""Offline tests use named fixtures. Actual speech and inference live in probe-voice.py."""
import asyncio
import base64
import io
import json
import wave

from fastapi.testclient import TestClient
import httpx
import pytest

from portfolio_core.ollama import ModelServiceError, OllamaClient
from projects.p02_voice_agent.app import create_app
from projects.p02_voice_agent.audio import read_wav, write_wav
from projects.p02_voice_agent.config import MAX_INPUT

ORIGIN = 'http://127.0.0.1:8102'
PATH = '/api/turn/' + 'a' * 32
HEADERS = {'Content-Type': 'audio/wav'}
PCM = b'\xe8\x03\x18\xfc' * 4000
WAV = write_wav(PCM)


class FixtureSTT:
    name = 'fixture STT'

    def __init__(self, text='A fictional question.'):
        self.text = text
        self.calls = 0

    def ready(self):
        return True

    async def transcribe(self, pcm):
        self.calls += 1
        assert pcm == PCM
        return {'text': self.text, 'model_load_ms': 0, 'decode_ms': 0}


class FixtureSpeech:
    name = 'fixture speech'

    def ready(self):
        return True

    async def synthesize(self, text):
        assert text.strip()
        return WAV


class FixtureModel:
    def __init__(self, parts=('This is one sentence.', ' Another follows.')):
        self.parts = parts
        self.calls = 0
        self.closed = False

    async def stream_chat(self, model, messages):
        self.calls += 1
        try:
            for part in self.parts:
                yield part
        finally:
            self.closed = True


def client(stt=None, speech=None, model_client=None):
    app = create_app(stt or FixtureSTT(), speech or FixtureSpeech(), model_client or FixtureModel(), 'fixture-model')
    return TestClient(app, base_url=ORIGIN)


def events(response):
    assert response.status_code == 200
    return [json.loads(line) for line in response.iter_lines() if line]


def test_stream_orders_transcript_deltas_and_two_audio_chunks():
    response = client().post(PATH, content=WAV, headers=HEADERS)
    stream = events(response)
    assert response.headers['content-type'].startswith('application/x-ndjson')
    assert response.headers['cache-control'] == 'no-store'
    assert [e['type'] for e in stream] == ['stage', 'transcript', 'stage', 'delta', 'audio', 'delta', 'audio', 'done']
    assert read_wav(base64.b64decode(stream[4]['wav_base64'])) == PCM
    assert stream[-1]['audio_chunks'] == 2
    timing = stream[-1]['timing']
    assert timing['stt_ms'] <= timing['first_audio_ms'] <= timing['total_ms']


@pytest.mark.parametrize(('payload', 'headers', 'expected'), [
    (WAV, {'Content-Type': 'text/plain'}, 415),
    (b'x' * (MAX_INPUT + 1), HEADERS, 413),
    (b'broken', HEADERS, 422),
    (WAV[:-4], HEADERS, 422),
    (write_wav(bytes(16000)), HEADERS, 422),
    (write_wav(PCM[:200]), HEADERS, 422),
    (WAV, {**HEADERS, 'Origin': 'https://example.invalid'}, 403),
    (WAV, {**HEADERS, 'Host': 'other.invalid'}, 400),
])
def test_invalid_requests_never_reach_speech_recognition(payload, headers, expected):
    stt = FixtureSTT()
    assert client(stt).post(PATH, content=payload, headers=headers).status_code == expected
    assert stt.calls == 0


def test_wrong_wave_format_is_refused():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, 48000, 0, 'NONE', ''))
        stream.writeframes(PCM)
    assert client().post(PATH, content=output.getvalue(), headers=HEADERS).status_code == 422


def test_missing_setup_refuses_a_turn():
    class Missing(FixtureSTT):
        def ready(self):
            return False

    stt = Missing()
    assert client(stt).post(PATH, content=WAV, headers=HEADERS).status_code == 503
    assert stt.calls == 0


def test_empty_transcript_stops_before_model():
    model = FixtureModel()
    stream = events(client(FixtureSTT(''), model_client=model).post(PATH, content=WAV, headers=HEADERS))
    assert stream[-1]['type'] == 'error'
    assert 'No speech' in stream[-1]['message']
    assert model.calls == 0


def test_reply_cap_closes_provider_and_bounds_speech():
    model = FixtureModel(('x' * 600, 'outside the cap'))
    stream = events(client(model_client=model).post(PATH, content=WAV, headers=HEADERS))
    assert stream[-1]['clipped'] is True
    assert stream[-1]['audio_chunks'] == 1
    assert sum(len(e['text']) for e in stream if e['type'] == 'delta') == 500
    assert model.closed


def test_cancel_releases_busy_slot_and_is_scoped_to_the_active_id():
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()

        class Blocking(FixtureSTT):
            async def transcribe(self, pcm):
                started.set()
                try:
                    await asyncio.sleep(30)
                finally:
                    cancelled.set()

        model = FixtureModel()
        app = create_app(Blocking(), FixtureSpeech(), model, 'fixture-model')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as http:
            pending = asyncio.create_task(http.post(PATH, content=WAV, headers=HEADERS))
            await asyncio.wait_for(started.wait(), 2)
            other = '/api/turn/' + 'b' * 32
            assert (await http.post(other, content=WAV, headers=HEADERS)).status_code == 409
            assert (await http.delete(other)).json() == {'cancelled': False}
            assert (await http.delete(PATH)).json() == {'cancelled': True}
            result = await asyncio.wait_for(pending, 2)
            assert events(result)[-1]['type'] == 'cancelled'
            assert cancelled.is_set()
            assert not (await http.get('/health')).json()['busy']
            assert model.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize('body', ['{"message":{"content":"Hello"}}\n', '{not-json}\n', '{"error":"bad"}\n'])
def test_provider_stream_requires_valid_completion(body):
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
        model = OllamaClient('http://127.0.0.1:11435', transport=transport)
        with pytest.raises(ModelServiceError):
            _ = [delta async for delta in model.stream_chat('fixture', [])]

    asyncio.run(scenario())


def test_provider_stream_returns_deltas_and_closes_on_done():
    async def scenario():
        def respond(request):
            assert json.loads(request.content)['stream'] is True
            return httpx.Response(200, text='{"message":{"content":"Hi"},"done":false}\n{"done":true}\n')

        model = OllamaClient('http://127.0.0.1:11435', transport=httpx.MockTransport(respond), num_gpu=0)
        assert [delta async for delta in model.stream_chat('fixture', [])] == ['Hi']

    asyncio.run(scenario())
