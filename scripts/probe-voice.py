"""Actual CPU recognition, streamed Ollama reply, Windows speech and cancellation."""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.p02_voice_agent.adapters import WindowsSpeech
from projects.p02_voice_agent.audio import read_wav, speech_rms, write_wav
from projects.p02_voice_agent.config import MODEL_ID, MODEL_PATH, MODEL_REVISION, SAMPLE_RATE

HEADERS = {'Content-Type': 'audio/wav'}


def ms(start):
    return round((perf_counter() - start) * 1000)


async def observe(client, recording):
    audio = []
    events = []
    reply = []
    started = perf_counter()
    async with client.stream('POST', '/api/turn/' + uuid.uuid4().hex, content=recording, headers=HEADERS) as response:
        if response.is_error:
            await response.aread()
            raise RuntimeError(f'Voice endpoint returned {response.status_code}: {response.json()}')
        async for line in response.aiter_lines():
            event = json.loads(line)
            if event['type'] == 'heartbeat':
                continue
            if event['type'] == 'delta':
                reply.append(event['text'])
            if event['type'] == 'audio':
                wav = base64.b64decode(event.pop('wav_base64'), validate=True)
                pcm = read_wav(wav, seconds=60)
                assert speech_rms(pcm) > 0.002, 'Speech output was silent.'
                audio.append(pcm)
                event.update(bytes=len(wav), duration_ms=round(len(pcm) / 32), sha256=hashlib.sha256(wav).hexdigest())
            events.append({**event, 'received_ms': ms(started)})
    return events, ''.join(reply), audio


async def cancel_turn(client, recording, *, disconnect=False, after_delta=False):
    turn_id = uuid.uuid4().hex
    path = '/api/turn/' + turn_id
    started = perf_counter()
    async with client.stream('POST', path, content=recording, headers=HEADERS) as response:
        response.raise_for_status()
        events = response.aiter_lines()
        first = json.loads(await anext(events))
        assert first == {'type': 'stage', 'stage': 'transcribing'}
        if after_delta:
            async for line in events:
                if json.loads(line)['type'] == 'delta':
                    break
            else:
                raise AssertionError('No live model delta to cancel.')
        else:
            await asyncio.sleep(0.2)
        assert (await client.get('/health')).json()['busy']
        if not disconnect:
            cancellation = await client.delete(path)
            assert cancellation.status_code == 202 and cancellation.json()['cancelled']
            tail = [json.loads(line)['type'] async for line in events]
            assert 'cancelled' in tail and 'audio' not in tail and 'done' not in tail
    for _ in range(30):
        if not (await client.get('/health')).json()['busy']:
            return {'passed': True, 'mode': 'client disconnect' if disconnect else 'explicit cancel',
                    'after': 'first model delta' if after_delta else 'transcription started',
                    'released_ms_from_turn_start': ms(started)}
        await asyncio.sleep(0.05)
    raise AssertionError('Cancelled voice turn did not release the active slot.')


async def main():
    voice = WindowsSpeech()
    case_inputs = [
        ('single_fact', 'What is the capital of France? Please answer in one short sentence.', ('capital', 'france'), ('paris',), 1),
        ('two_sentences', 'Please repeat exactly: The library is open. Read a book today.', ('library', 'book'), ('library', 'book'), 2),
    ]
    with (MODEL_PATH / 'model.bin').open('rb') as weights:
        weights_sha = hashlib.file_digest(weights, 'sha256').hexdigest()
    evidence = {'captured_at': datetime.now(timezone.utc).isoformat(), 'mode': 'real CPU voice API with synthetic English input',
                'stt_model': MODEL_ID, 'stt_revision': MODEL_REVISION, 'stt_weights_sha256': weights_sha,
                'voice': voice.name, 'cases': [], 'complete': False}
    target = ROOT / 'docs' / 'voice-live.json'

    def save():
        target.write_text(json.dumps(evidence, indent=2), encoding='utf8', newline='\n')

    async with httpx.AsyncClient(base_url='http://127.0.0.1:8102', timeout=65, trust_env=False) as client:
        assert (await client.get('/health')).json()['service'] == 'voice-agent'
        for label, question, transcript_terms, answer_terms, minimum_chunks in case_inputs:
            input_pcm = read_wav(await voice.synthesize(question))
            pcm = bytes(SAMPLE_RATE) + input_pcm + bytes(SAMPLE_RATE // 2)
            recording = write_wav(pcm)
            events, answer, speech = await observe(client, recording)
            transcript = next((event['text'] for event in events if event['type'] == 'transcript'), '')
            done = next((event for event in events if event['type'] == 'done'), None)
            passed = (done is not None and all(term in transcript.lower() for term in transcript_terms)
                      and all(term in answer.lower() for term in answer_terms) and len(speech) >= minimum_chunks)
            case = {'id': label, 'passed': passed, 'spoken_input': question, 'transcript': transcript,
                    'reply': answer, 'input_wav_sha256': hashlib.sha256(recording).hexdigest(),
                    'input_duration_ms': round(len(pcm) / 32), 'events': events, 'done': done}
            evidence['cases'].append(case)
            save()
            print(json.dumps({key: case[key] for key in ('id', 'passed', 'transcript', 'reply', 'done')}), flush=True)
            assert passed, 'Live voice check failed. See docs/voice-live.json.'
            if label == 'single_fact':
                browser_input = pcm + bytes(2 * SAMPLE_RATE * 10 - len(pcm))
                (ROOT / '.runtime' / 'voice-fake-mic.wav').write_bytes(write_wav(browser_input))
                evidence['cancel'] = await cancel_turn(client, recording)
                evidence['disconnect'] = await cancel_turn(client, recording, disconnect=True)
                evidence['cancel_after_delta'] = await cancel_turn(client, recording, after_delta=True)
            if label == 'two_sentences':
                demo = write_wav(pcm + bytes(SAMPLE_RATE) + b''.join(speech))
                (ROOT / 'docs' / 'voice-demo.wav').write_bytes(demo)
                evidence['demo_sha256'] = hashlib.sha256(demo).hexdigest()
                evidence['demo_duration_ms'] = round((len(demo) - 44) / 32)
        evidence.update(complete=True, passed=True)
        save()
        print(json.dumps({'cancel': evidence['cancel'], 'disconnect': evidence['disconnect'],
                          'cancel_after_delta': evidence['cancel_after_delta'],
                          'demo_duration_ms': evidence['demo_duration_ms']}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
