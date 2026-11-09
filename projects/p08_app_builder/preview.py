"""Separate-origin preview. Each API request replays a bounded journal in a fresh OCI container."""
import asyncio
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,HTMLResponse,JSONResponse,Response

from .store import BuildStore
from .runtime import IsolationError,execute
from .web import boundaries

STATIC=Path(__file__).with_name('static')


def artifacts(store,run_id):
    run=store.get(run_id)
    if run['status']!='passed':raise ValueError('Only a passing build can be previewed.')
    workspace=store.workspace(run_id);files={}
    for name,digest in run['manifest']['files'].items():
        if name not in ('backend.py','App.jsx'):raise ValueError('Unknown generated source file.')
        path=workspace.path/name
        if path.is_symlink() or path.stat().st_size>16000:raise ValueError('Unsafe source artifact.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Source changed since validation; regenerate it.')
        files[name]=data.decode('utf8')
    if set(files)!={'backend.py','App.jsx'}:raise ValueError('Both source artifacts are required.')
    bundle=workspace.path/'app.js'
    if bundle.is_symlink() or bundle.stat().st_size>512000 or hashlib.sha256(bundle.read_bytes()).hexdigest()!=run['bundle_sha256']:
        raise ValueError('Built bundle changed since validation.')
    return run,workspace,files


def create_app(store=None,executor=None):
    store=store or BuildStore(os.getenv('APP_BUILDER_STATE'));executor=executor or execute
    app=FastAPI(title='Isolated generated preview',docs_url=None,redoc_url=None);slot=asyncio.Semaphore(1)
    # React handles submit events with fetch. CSP still prevents native form navigation.
    boundaries(app,"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors http://127.0.0.1:8108; sandbox allow-scripts allow-same-origin allow-forms")
    def load(run_id):
        try:return artifacts(store,run_id)
        except (ValueError,OSError,KeyError) as exc:raise HTTPException(409,'Preview unavailable: build artifacts must match a passing run.') from exc

    @app.get('/health')
    async def health():return {'status':'ok','service':'generated-preview','journal_limit':30}

    @app.get('/r/{run_id}/',response_class=HTMLResponse)
    async def shell(run_id:str):
        run,_,_=load(run_id)
        title = escape(run['spec']['title'])
        item_label = escape(run['spec']['item_label'])
        return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<link rel="stylesheet" href="style.css"><script src="app.js" defer></script><script src="controls.js" defer></script>
</head><body><aside>GENERATED PREVIEW · 30 REQUEST LIMIT <button id="reset-preview" type="button">Reset preview</button></aside>
<div id="root" data-title="{title}" data-item-label="{item_label}"></div></body></html>'''

    @app.get('/r/{run_id}/app.js')
    async def bundle(run_id:str):
        _,workspace,_=load(run_id);return FileResponse(workspace.path/'app.js',media_type='application/javascript')

    @app.get('/r/{run_id}/style.css')
    async def style(run_id:str):
        load(run_id);return FileResponse(STATIC/'preview.css')

    @app.get('/r/{run_id}/controls.js')
    async def controls(run_id:str):
        load(run_id);return Response("document.getElementById('reset-preview').addEventListener('click',async()=>{const r=await fetch('reset',{method:'POST'});if(r.ok)location.reload();});",media_type='application/javascript')

    @app.post('/r/{run_id}/reset')
    async def reset(run_id:str):
        _,workspace,_=load(run_id)
        try:await asyncio.wait_for(slot.acquire(),timeout=0.05)
        except TimeoutError as exc:raise HTTPException(429,'A preview request is running.') from exc
        try:
            path=workspace.path/'preview-journal.json'
            if path.exists():path.unlink()
            return {'status':'reset'}
        finally:slot.release()

    async def forward(run_id,request,item_id=None):
        _,workspace,files=load(run_id)
        body = await request.body() if request.method != 'GET' else b''
        if len(body)>1000:raise HTTPException(413,'Preview body exceeds one thousand bytes.')
        if item_id is not None and not 1<=item_id<=999999:raise HTTPException(404,'Item not found.')
        call={'method':request.method,'path':'/api/items'+('/'+str(item_id) if item_id is not None else '')}
        if body:
            try:
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError('Expected an object.')
                json.dumps(value, allow_nan=False)
                call['body'] = value
            except ValueError as exc:raise HTTPException(422,'Use a JSON body.') from exc
        try:await asyncio.wait_for(slot.acquire(),timeout=0.05)
        except TimeoutError as exc:raise HTTPException(429,'Another preview request is running.') from exc
        try:
            path=workspace.path/'preview-journal.json'
            journal=json.loads(path.read_text()) if path.is_file() else {'requests':[],'responses':[],'durations_ms':[]}
            if len(journal['requests'])>=30:raise HTTPException(409,'Preview reached thirty requests. Reset it to continue.')
            calls=journal['requests']+[call]
            execution=await asyncio.to_thread(executor,{'op':'backend_request','files':files,'requests':calls})
            result=execution.get('result') or {};responses=result.get('responses')
            if execution['exit_code'] or execution.get('termination_reason') or not isinstance(responses,list) or len(responses)!=len(calls):
                raise HTTPException(503,'The isolated preview failed or reached a runtime limit.')
            if responses[:-1]!=journal['responses']:raise HTTPException(409,'Preview replay changed an earlier result; reset or regenerate this app.')
            latest=responses[-1]
            if not isinstance(latest,dict) or type(latest.get('status')) is not int or not 200<=latest['status']<=599:
                raise HTTPException(503,'Invalid isolated response.')
            journal={'requests':calls,'responses':responses,'durations_ms':journal['durations_ms']+[execution['duration_ms']]}
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(journal,indent=2),encoding='utf8',newline='\n');temporary.replace(path)
            if latest['status']==204:return Response(status_code=204)
            return JSONResponse(latest.get('body'),status_code=latest['status'])
        except IsolationError as exc:raise HTTPException(503,str(exc)) from exc
        except ValueError as exc:raise HTTPException(409,'Preview input exceeded its replay bounds.') from exc
        finally:slot.release()

    @app.api_route('/r/{run_id}/api/items',methods=['GET','POST'])
    async def collection(run_id:str,request:Request):return await forward(run_id,request)

    @app.api_route('/r/{run_id}/api/items/{item_id}',methods=['PATCH','DELETE'])
    async def item(run_id:str,item_id:int,request:Request):return await forward(run_id,request,item_id)
    return app


app=create_app()
