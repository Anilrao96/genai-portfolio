"""Expose Clearflow's fixed routes on Windows loopback through the owned WSL session."""
import asyncio
import re

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .native import COMPOSE_PROJECT, DockerError, docker
from .transport import RESPONSE_HEADERS

READ_PATHS = {'/', '/health', '/api/config', '/api/models', '/api/snapshot', '/api/history',
              '/static/app.js', '/static/style.css'}
WRITE_PATHS = {'/api/ingest', '/api/rollback'}
BATCH_PATH = r'/api/batches/[0-9a-f]{32}'


def forward(project, method, path, body):
    result = docker('exec', '-i', f'{project}-agent-1', 'python', '-m', 'projects.p09_docker_agent.transport',
                    method, path, payload=body, timeout=210)
    return result.stdout


def parse_response(raw):
    block, separator, content = raw.partition(b'\r\n\r\n')
    first, *lines = block.decode('latin-1').split('\r\n')
    match = re.fullmatch(r'HTTP/1\.[01] ([2-5][0-9]{2})(?: .*)?', first)
    if not separator or not match:
        raise DockerError('Invalid HTTP response from the Compose service.')
    headers = {}
    for line in lines:
        key, _, value = line.partition(':')
        if key.lower() in RESPONSE_HEADERS:
            headers[key.lower()] = value.strip()
    return Response(content, status_code=int(match[1]), headers=headers)


def create_relay(project=COMPOSE_PROJECT, connector=forward):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
    slots = asyncio.Semaphore(4)

    @app.api_route('/{path:path}', methods=['GET', 'POST'])
    async def relay(path: str, request: Request):
        path = '/' + path
        method = request.method
        if method == 'GET':
            allowed = path in READ_PATHS or re.fullmatch(BATCH_PATH, path)
        else:
            allowed = path in WRITE_PATHS or re.fullmatch(BATCH_PATH + '/replay', path)
        if not allowed or request.url.query:
            raise HTTPException(404, 'Unknown Clearflow route.')
        body = bytearray()
        if method == 'POST':
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                raise HTTPException(403, 'Cross-origin requests are not allowed.')
            if request.headers.get('content-type', '').split(';', 1)[0].lower().strip() != 'application/json':
                raise HTTPException(415, 'Use application/json.')
            async for chunk in request.stream():
                if len(body) + len(chunk) > 65000:
                    raise HTTPException(413, 'Request is too large.')
                body.extend(chunk)
        async with slots:
            try:
                raw = await asyncio.to_thread(connector, project, method, path, bytes(body))
                return parse_response(raw)
            except DockerError as error:
                raise HTTPException(503, 'The local Compose service is unavailable.') from error

    return app
