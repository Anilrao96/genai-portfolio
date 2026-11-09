"""Loopback voice API. A disconnected or cancelled client releases the active turn."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Annotated

from anyio import CancelScope
from fastapi import FastAPI, HTTPException, Path as PathParam, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import OllamaClient

from .adapters import WhisperSTT, WindowsSpeech
from .audio import VoiceError, read_wav, speech_rms
from .config import DEFAULT_CHAT, DEFAULT_VOICE, MAX_INPUT, MAX_SECONDS, SAMPLE_RATE
from .turn import VoiceTurn

STATIC = Path(__file__).with_name('static')
TurnID = Annotated[str, PathParam(pattern=r'^[a-f0-9]{32}$')]
CSP = "default-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'"


@dataclass
class ActiveTurn:
    identifier: str
    task: asyncio.Task


def create_app(stt=None, speech=None, model_client=None, model=None):
    stt = stt if stt is not None else WhisperSTT()
    speech = speech if speech is not None else WindowsSpeech(os.getenv('VOICE_TTS_NAME', DEFAULT_VOICE))
    model_client = model_client if model_client is not None else OllamaClient(
        os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11435'), num_gpu=0)
    engine = VoiceTurn(stt, model_client, speech, model or os.getenv('VOICE_MODEL', DEFAULT_CHAT))
    app = FastAPI(title='Relay · Local Voice Agent', docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])
    active = None

    @app.middleware('http')
    async def boundaries(request: Request, call_next):
        if request.method in ('POST', 'DELETE'):
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': 'Use the local Relay page to send voice requests.'}, status_code=403)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'Content-Security-Policy': CSP,
                                 'Permissions-Policy': 'microphone=(self)', 'X-Content-Type-Options': 'nosniff'})
        return response

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'service': 'voice-agent', 'busy': active is not None and not active.task.done()}

    @app.get('/api/config')
    async def config():
        return {'max_seconds': MAX_SECONDS, 'sample_rate': SAMPLE_RATE, 'model': engine.model,
                'stt': stt.name, 'speech': speech.name, 'stt_ready': stt.ready(), 'speech_ready': speech.ready()}

    @app.delete('/api/turn/{turn_id}', status_code=202)
    async def cancel(turn_id: TurnID):
        matched = active is not None and active.identifier == turn_id and not active.task.done()
        if matched:
            active.task.cancel()
        return {'cancelled': matched}

    @app.post('/api/turn/{turn_id}')
    async def turn(turn_id: TurnID, request: Request):
        nonlocal active
        if active is not None and not active.task.done():
            raise HTTPException(409, 'Another voice turn is still running.')
        if request.headers.get('content-type', '').split(';')[0] not in ('audio/wav', 'audio/x-wav'):
            raise HTTPException(415, 'Send PCM WAV audio.')
        if not stt.ready() or not speech.ready():
            raise HTTPException(503, 'Complete local speech setup before recording.')
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_INPUT:
                raise HTTPException(413, 'The recording exceeds the audio size limit.')
            payload.extend(chunk)
        try:
            pcm = read_wav(payload)
            if speech_rms(pcm) < 0.002:
                raise VoiceError('The recording is too quiet. Check your microphone and try again.')
        except VoiceError as error:
            raise HTTPException(422, str(error)) from error
        # The body read can yield control to another request.
        if active is not None and not active.task.done():
            raise HTTPException(409, 'Another voice turn is still running.')
        queue = asyncio.Queue(maxsize=8)

        async def produce():
            try:
                async for event in engine.events(pcm):
                    await queue.put(event)
            except Exception:
                await queue.put({'type': 'error', 'message': 'The local voice stage failed. Retry the turn.'})

        task = asyncio.create_task(produce())
        active = ActiveTurn(turn_id, task)

        def release(finished):
            nonlocal active
            if active is not None and active.task is finished:
                active = None

        task.add_done_callback(release)

        async def deliver():
            try:
                while not task.done() or not queue.empty():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except TimeoutError:
                        if task.done():
                            break
                        event = {'type': 'heartbeat'}
                    yield json.dumps(event, separators=(',', ':')) + '\n'
                if task.cancelled():
                    yield '{"type":"cancelled"}\n'
            finally:
                if not task.done():
                    task.cancel()
                    with CancelScope(shield=True), suppress(asyncio.CancelledError):
                        await task

        return StreamingResponse(deliver(), media_type='application/x-ndjson', headers={'X-Accel-Buffering': 'no'})

    @app.get('/', include_in_schema=False)
    async def index():
        return FileResponse(STATIC / 'index.html')

    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    return app


app = create_app()
