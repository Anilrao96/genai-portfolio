import asyncio
import os
from pathlib import Path

from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field

from portfolio_core.ollama import OllamaClient,ModelServiceError,chat_models
from .backend import BackendRole
from .builder import AppBuilder
from .contracts import AppSpec, DEFAULT_MODEL
from .frontend import FrontendRole
from .qa import QARole
from .store import BuildStore
from .runtime import IsolationError,ready
from .web import boundaries

STATIC=Path(__file__).with_name('static')


class BuildRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    spec:AppSpec
    model:str=Field(default=DEFAULT_MODEL,min_length=1,max_length=120,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')


def create_app(store=None,roles=None,executor=None,guard=None,catalog=None):
    store=store or BuildStore(os.getenv('APP_BUILDER_STATE'))
    guard=guard or ready
    roles=roles or (lambda model:(BackendRole(model),FrontendRole(model),QARole(model)))
    catalog=catalog or OllamaClient(os.getenv('OLLAMA_BASE_URL','http://127.0.0.1:11435'))
    app=FastAPI(title='Assembly — local full-stack app builder',version='1.0.0');slot=asyncio.Semaphore(1)
    boundaries(app,"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src http://127.0.0.1:8118; frame-ancestors 'none'; base-uri 'none'")

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'service': 'app-builder', 'generator': 'direct-source-v1'}

    @app.get('/api/runtime')
    async def runtime():
        try:return {'ready':True,'proof':await asyncio.to_thread(guard)}
        except IsolationError as exc:return {'ready':False,'error':str(exc)}

    @app.get('/api/models')
    async def models():
        try:return {'models':chat_models(await catalog.models()), 'default_model': DEFAULT_MODEL}
        except ModelServiceError as exc:raise HTTPException(503,str(exc)) from exc

    @app.get('/api/runs')
    async def runs():return {'runs':await asyncio.to_thread(store.history)}

    @app.get('/api/runs/{run_id}')
    async def details(run_id:str):
        try:return await asyncio.to_thread(store.get,run_id)
        except ValueError as exc:raise HTTPException(404,'Build not found.') from exc

    @app.post('/api/build')
    async def build(body:BuildRequest):
        try:await asyncio.wait_for(slot.acquire(),timeout=0.05)
        except TimeoutError as exc:raise HTTPException(429,'Another build is running.') from exc
        try:
            await asyncio.to_thread(guard)
            if body.model not in {m['name'] for m in chat_models(await catalog.models())}:raise HTTPException(422,'Select an installed local chat model.')
            backend,frontend,qa=roles(body.model)
            return await AppBuilder(backend,frontend,qa,store,executor,guard).run(body.spec,body.model)
        except (IsolationError,ModelServiceError) as exc:raise HTTPException(503,str(exc)) from exc
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        finally:slot.release()

    @app.get('/',include_in_schema=False)
    async def index():return FileResponse(STATIC/'index.html')
    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app


app=create_app()
