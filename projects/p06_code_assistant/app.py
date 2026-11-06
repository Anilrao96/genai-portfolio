import asyncio
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field,field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import OllamaClient,ModelServiceError,chat_models
from .assistant import CodeAssistant,CodeModel
from .runs import RunStore
from .sandbox import IsolationError,VerifiedSandbox
from .tasks import TASKS

STATIC=Path(__file__).with_name('static')


class RunRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    task_id:Literal['mean','words']
    model:str=Field(default='qwen3:4b',min_length=1,max_length=120,pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$')
    starting_code:str=Field(default='',max_length=6000)
    @field_validator('starting_code')
    @classmethod
    def bound_bytes(cls,value):
        if len(value.encode('utf8'))>6000:raise ValueError('Code exceeds six thousand UTF-8 bytes.')
        return value


def create_app(store=None,model_factory=None,sandbox=None,catalog=None):
    store=store or RunStore(os.getenv('CODE_RUNS_PATH'))
    factory=model_factory or CodeModel;sandbox=sandbox or VerifiedSandbox()
    catalog=catalog or OllamaClient(os.getenv('OLLAMA_BASE_URL','http://127.0.0.1:11435'))
    app=FastAPI(title='Repair Bench — isolated code assistant',version='1.0.0');slot=asyncio.Semaphore(1)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])

    @app.middleware('http')
    async def boundaries(request:Request,call_next):
        if request.method=='POST':
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin requests are not allowed.'},status_code=403)
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>32000:return JSONResponse({'detail':'Request is too large.'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.get('/health')
    async def health():return {'status':'ok','service':'code-assistant','execution_protocol':'verified-wsl-oci-v1'}

    @app.get('/api/tasks')
    async def tasks():return {'tasks':[{'id':key,**value} for key,value in TASKS.items()],'default_model':'qwen3:4b'}

    @app.get('/api/runtime')
    async def runtime():
        try:
            proof=await asyncio.to_thread(sandbox.ready)
            return {'ready':True,'backend':'Native WSL OCI containers','proof':proof}
        except IsolationError as exc:return {'ready':False,'backend':'Native WSL OCI containers','error':str(exc)}

    @app.get('/api/models')
    async def models():
        try:return {'models':chat_models(await catalog.models())}
        except ModelServiceError as exc:raise HTTPException(503,str(exc)) from exc

    @app.get('/api/runs')
    async def history():return {'runs':await asyncio.to_thread(store.history)}

    @app.get('/api/runs/{run_id}')
    async def details(run_id:str):
        try:return await asyncio.to_thread(store.get,run_id)
        except ValueError as exc:raise HTTPException(404,'Run not found.') from exc

    @app.post('/api/run')
    async def run(body:RunRequest):
        try:await asyncio.wait_for(slot.acquire(),timeout=0.05)
        except TimeoutError as exc:raise HTTPException(429,'Another repair is running. Try again shortly.') from exc
        try:
            await asyncio.to_thread(sandbox.ready)
            if body.model not in {m['name'] for m in chat_models(await catalog.models())}:
                raise HTTPException(422,'Select an installed local chat model.')
            return await CodeAssistant(factory(body.model),store,sandbox).run(body.task_id,body.model,body.starting_code)
        except (IsolationError,ModelServiceError) as exc:raise HTTPException(503,str(exc)) from exc
        except ValueError as exc:raise HTTPException(409,str(exc)) from exc
        finally:slot.release()

    @app.get('/',include_in_schema=False)
    async def index():return FileResponse(STATIC/'index.html')
    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app


app=create_app()
