"""Streaming voice turn with explicit stage timing and bounded output."""
import asyncio
import base64
from contextlib import aclosing
import re
from time import perf_counter

from portfolio_core.ollama import ModelServiceError

from .audio import VoiceError

MAX_REPLY = 500
MAX_CHUNKS = 3
SENTENCE_END = re.compile(r'[.!?](?=\s|$)')


def milliseconds(start):
    return round((perf_counter() - start) * 1000)


class VoiceTurn:
    def __init__(self, stt, model_client, speech, model):
        self.stt = stt
        self.model_client = model_client
        self.speech = speech
        self.model = model

    async def events(self, pcm):
        started = perf_counter()
        timing = {'stt_ms': 0, 'model_wait_ms': 0, 'tts_ms': 0,
                  'first_token_ms': None, 'first_audio_ms': None}
        reply = ''
        pending = ''
        chunks = 0
        clipped = False

        async def speak(text):
            nonlocal chunks
            start = perf_counter()
            wave = await self.speech.synthesize(text.strip())
            timing['tts_ms'] += milliseconds(start)
            chunks += 1
            if timing['first_audio_ms'] is None:
                timing['first_audio_ms'] = milliseconds(started)
            return {'type': 'audio', 'index': chunks, 'wav_base64': base64.b64encode(wave).decode('ascii'),
                    'elapsed_ms': milliseconds(started)}

        try:
            async with asyncio.timeout(55):
                yield {'type': 'stage', 'stage': 'transcribing'}
                transcript = await self.stt.transcribe(pcm)
                timing['stt_ms'] = milliseconds(started)
                text = transcript['text'].strip()
                if not text:
                    raise VoiceError('No speech was recognized. Try speaking closer to the microphone.')
                yield {'type': 'transcript', 'text': text, 'elapsed_ms': timing['stt_ms'],
                       'model_load_ms': transcript.get('model_load_ms'), 'decode_ms': transcript.get('decode_ms')}

                messages = [
                    {'role': 'system', 'content': 'You are a brief spoken assistant. Answer directly in one or two short sentences, using plain text.'},
                    {'role': 'user', 'content': text},
                ]
                model_started = perf_counter()
                yield {'type': 'stage', 'stage': 'replying'}
                async with aclosing(self.model_client.stream_chat(self.model, messages)) as deltas:
                    while len(reply) < MAX_REPLY:
                        waiting = perf_counter()
                        try:
                            delta = await anext(deltas)
                        except StopAsyncIteration:
                            timing['model_wait_ms'] += milliseconds(waiting)
                            break
                        timing['model_wait_ms'] += milliseconds(waiting)
                        if timing['first_token_ms'] is None:
                            timing['first_token_ms'] = milliseconds(model_started)
                        available = MAX_REPLY - len(reply)
                        clipped = len(delta) > available
                        delta = delta[:available]
                        reply += delta
                        pending += delta
                        yield {'type': 'delta', 'text': delta, 'first_token_ms': timing['first_token_ms']}
                        boundary = SENTENCE_END.search(pending)
                        if boundary and boundary.end() >= 12 and chunks < MAX_CHUNKS - 1:
                            sentence, pending = pending[:boundary.end()], pending[boundary.end():]
                            yield await speak(sentence)
                    else:
                        clipped = True

                if not reply.strip():
                    raise VoiceError('The local model returned an empty reply.')
                if pending.strip():
                    yield await speak(pending)
                yield {'type': 'done', 'model': self.model, 'audio_chunks': chunks, 'clipped': clipped,
                       'timing': {**timing, 'total_ms': milliseconds(started)}}
        except (VoiceError, ModelServiceError) as error:
            yield {'type': 'error', 'message': str(error)}
        except TimeoutError:
            yield {'type': 'error', 'message': 'The voice turn took too long. Try a shorter question.'}
