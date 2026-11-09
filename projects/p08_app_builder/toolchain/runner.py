"""Trusted OCI entrypoint; only this file and dependency locks enter the image build context.

Generated files enter stdin after policy checks, never a Dockerfile, build script or host mount.
"""
import asyncio
import base64
import contextlib
import ctypes
import importlib.util
import inspect
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import traceback
import time

WIRE=sys.stdout


def policy():
    if ctypes.CDLL(None).prctl(38,1,0,0,0)!=0:raise RuntimeError('Cannot set no-new-privileges.')
    status=Path('/proc/self/status').read_text()
    limits={name:list(resource.getrlimit(kind)) for name,kind in [('cpu',resource.RLIMIT_CPU),('as',resource.RLIMIT_AS),
        ('nproc',resource.RLIMIT_NPROC),('fsize',resource.RLIMIT_FSIZE),('nofile',resource.RLIMIT_NOFILE)]}
    expected={'cpu':[8,8],'as':[2147483648,2147483648],'nproc':[32,32],'fsize':[2097152,2097152],'nofile':[128,128]}
    if (os.getuid()!=65534 or 'CapEff:\t0000000000000000' not in status or 'NoNewPrivs:\t1' not in status
        or os.listdir('/sys/class/net')!=['lo'] or limits!=expected):raise RuntimeError('Kernel isolation policy mismatch.')
    return {'uid':os.getuid(),'capabilities_effective':0,'no_new_privileges':True,'interfaces':['lo'],'limits':limits}


def backend_limits():
    resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456))
    resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    values={'address_space':list(resource.getrlimit(resource.RLIMIT_AS)),'processes':list(resource.getrlimit(resource.RLIMIT_NPROC)),
        'file_size':list(resource.getrlimit(resource.RLIMIT_FSIZE))}
    if values!={'address_space':[268435456,268435456],'processes':[1,1],'file_size':[0,0]}:raise RuntimeError('Backend hard limit mismatch.')
    return values


def controls():
    backend_limits()
    observed={'host_paths_absent':not any(Path(p).exists() for p in ['/mnt/c','/mnt/d','/var/run/docker.sock'])}
    try:socket.create_connection(('192.0.2.1',443),timeout=0.5);observed['network_errno']=None
    except OSError as exc:observed['network_errno']=exc.errno
    try:
        with open('/tmp/refused-data','w') as target:target.write('not allowed')
        observed['file_errno']=None
    except OSError as exc:observed['file_errno']=exc.errno
    try:subprocess.run(['/bin/true'],check=True);observed['process_errno']=None
    except OSError as exc:observed['process_errno']=exc.errno
    try:bytearray(512*1024*1024);observed['memory_refused']=False
    except MemoryError:observed['memory_refused']=True
    return observed


async def validate(request):
    files=request['files']
    if set(files)!={'backend.py','App.jsx'}:raise ValueError('Unexpected generated file path.')
    for name,source in files.items():
        if not isinstance(source,str) or not 20<=len(source.encode())<=16000:raise ValueError('Source bounds exceeded.')
        Path('/workspace',name).write_text(source,encoding='utf8')
    bundle=None
    if request['op']=='validate':
        Path('/workspace/main.jsx').write_bytes(Path('/opt/builder/entry.jsx').read_bytes())
        Path('/workspace/dist').mkdir()
        build=subprocess.run(['/opt/tool/node_modules/@esbuild/linux-x64/bin/esbuild','/workspace/main.jsx','--bundle','--minify',
            '--jsx=automatic','--platform=browser','--target=es2022','--define:process.env.NODE_ENV="production"',
            '--outfile=/workspace/dist/app.js'],capture_output=True,timeout=10)
        if build.returncode:return {'build_passed':False,'stage':'frontend_build','error':build.stderr.decode(errors='replace')[:3000]}
        bundle=Path('/workspace/dist/app.js').read_bytes()
        if len(bundle)>512000:raise ValueError('Built bundle exceeds 512KB.')
    active_limits=backend_limits() # Irreversible hard limits before importing any model-generated Python.
    import httpx
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    module_spec=importlib.util.spec_from_file_location('generated_backend','/workspace/backend.py')
    module=importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not isinstance(module.app,FastAPI):raise ValueError('Generated backend must expose a FastAPI app.')
    sync_routes = [route.path for route in module.app.routes
                   if isinstance(route, APIRoute) and not inspect.iscoroutinefunction(route.endpoint)]
    if sync_routes:
        return {'build_passed': False, 'stage': 'backend_contract',
                'error': f'Use async def for every route. Sync routes: {sync_routes}.'}
    results=[]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app,raise_app_exceptions=False),base_url='http://generated.local') as client:
        for case in request['requests']:
            response=await client.request(case['method'],case['path'],json=case.get('body'))
            body=response.content
            if len(body)>16000:raise ValueError('Backend response is too large.')
            try:
                decoded = json.loads(body) if body else None
            except ValueError:
                decoded = {'non_json_response': body[:250].decode('utf8', errors='replace')}
            results.append({'status':response.status_code,'body':decoded})
    result={'build_passed':True,'stage':'validated','responses':results,'backend_policy':active_limits,
        'transport':'actual HTTPX ASGI requests to generated FastAPI, inside native OCI container'}
    if bundle is not None:result.update(bundle_base64=base64.b64encode(bundle).decode(),bundle_bytes=len(bundle))
    return result


def main():
    kernel=policy()
    raw=sys.stdin.buffer.read(60001)
    if len(raw)>60000:raise ValueError('Input exceeds 60KB.')
    request=json.loads(raw)
    with contextlib.redirect_stdout(sys.stderr):
        if request['op']=='cpu_control':
            backend_limits()
            while True:pass
        elif request['op']=='wall_control':
            backend_limits();time.sleep(60)
        elif request['op']=='output_control':
            backend_limits()
            while True:print('x'*1024,flush=True)
        elif request['op']=='controls':result=controls()
        elif request['op'] in ('validate','backend_request'):result=asyncio.run(validate(request))
        else:raise ValueError('Unknown isolated operation.')
    result['kernel_policy']=kernel
    print(json.dumps(result,allow_nan=False),file=WIRE,flush=True)


if __name__=='__main__':
    try:main()
    except BaseException:
        traceback.print_exc(limit=8)
        sys.exit(1)
