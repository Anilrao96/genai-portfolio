"""One-shot app builds/ASGI requests in a fresh inspected container; no host source execution."""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid

from projects.p06_code_assistant.sandbox import IsolationError,command,verify_ready
from projects.p06_code_assistant.session import CLI,READY,ROOT,SESSION

MARKER=ROOT/'.runtime/app-toolchain.json'
PROOF=ROOT/'.runtime/app-isolation-verified.json'
INPUTS=('Dockerfile','.dockerignore','package.json','package-lock.json','requirements.txt','runner.py','entry.jsx')
LIMITS={'cpu':8,'as':2*1024**3,'nproc':32,'fsize':2*1024**2,'nofile':128}
MEMORY=384*1024**2


def context_hash():
    digest=hashlib.sha256()
    for name in INPUTS:
        path=ROOT/'projects/p08_app_builder/toolchain'/name
        if path.is_symlink() or not path.is_file():raise IsolationError('Trusted toolchain inputs are missing or linked.')
        digest.update(name.encode()+b'\0'+path.read_bytes().replace(b'\r\n',b'\n')+b'\0')
    return digest.hexdigest()


def image():
    verify_ready()
    if not MARKER.is_file():raise IsolationError('Run scripts/setup-app-toolchain.py before app generation.')
    marker=json.loads(MARKER.read_text())
    if marker['context_sha256']!=context_hash():raise IsolationError('Trusted toolchain changed; rebuild and reverify isolation.')
    if not re.fullmatch('sha256:[0-9a-f]{64}',marker['image_id']):raise IsolationError('Invalid app toolchain image.')
    return marker


def ready():
    marker=image()
    if not PROOF.is_file():raise IsolationError('App-specific isolation controls have not passed.')
    proof=json.loads(PROOF.read_text())
    if (not proof.get('passed') or proof.get('image_id')!=marker['image_id'] or proof.get('context_sha256')!=marker['context_sha256']
        or proof.get('creator_pid')!=json.loads(READY.read_text())['creator_pid']):raise IsolationError('App isolation proof is stale.')
    return proof


def inspect_policy(data,pinned):
    host=data['HostConfig'];config=data['Config']
    actual={item['Name']:(item['Soft'],item['Hard']) for item in host.get('Ulimits',[])}
    health=config.get('Healthcheck')
    if (data['Image']!=pinned or config['User']!='65534:65534' or host.get('NetworkMode')!='none'
        or host.get('Memory')!=MEMORY or host.get('NanoCpus')!=500_000_000
        or data.get('Mounts') or data.get('Ports') or (health and health.get('Test')!=['NONE'])
        or config.get('Entrypoint')!=['python','-I','-B','/opt/builder/runner.py']
        or any(actual.get(k)!=(v,v) for k,v in LIMITS.items())
        or config.get('Labels',{}).get('portfolio.project')!='p08_app_builder'):
        raise IsolationError('App container engine policy does not match the expected boundary.')


def execute(request,*,require_proof=True,wall_seconds=30):
    if require_proof:ready()
    pinned=image()['image_id'];payload=json.dumps(request,allow_nan=False).encode()
    if len(payload)>60000 or not 1<=wall_seconds<=30:raise ValueError('App execution input/time bound exceeded.')
    container=None;process=None
    try:
        args=['create','--interactive','--name','portfolio-app-'+uuid.uuid4().hex,'--label','portfolio.project=p08_app_builder',
            '--network','none','--user','65534:65534','--memory','384m','--cpus','0.5','--no-healthcheck','--pull','never']
        for key,value in LIMITS.items():args+=['--ulimit',f'{key}={value}:{value}']
        args.append(pinned)
        container=command(args).stdout.decode().strip()
        if not re.fullmatch('[0-9a-f]{64}',container):raise IsolationError('Unexpected app container identifier.')
        inspection=json.loads(command(['inspect',container,'--format','json']).stdout)[0]
        inspect_policy(inspection,pinned)
        process=subprocess.Popen([str(CLI),'--session',SESSION,'start','--attach','--interactive',container],cwd=ROOT,
            env={**os.environ,'TEMP':str(ROOT/'.runtime/temp'),'TMP':str(ROOT/'.runtime/temp')},
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        streams={'stdout':bytearray(),'stderr':bytearray()};excess=threading.Event()
        def drain(stream,key,maximum):
            while chunk:=stream.read1(4096):
                remaining=max(0,maximum-len(streams[key]));streams[key].extend(chunk[:remaining])
                if len(chunk)>remaining:excess.set()
        def write():
            try:process.stdin.write(payload);process.stdin.close()
            except (OSError,BrokenPipeError):pass
        readers=[threading.Thread(target=drain,args=(process.stdout,'stdout',768000),daemon=True),
                 threading.Thread(target=drain,args=(process.stderr,'stderr',16000),daemon=True)]
        for thread in readers:thread.start()
        writer=threading.Thread(target=write,daemon=True);writer.start();started=time.perf_counter();reason=None
        while process.poll() is None:
            if excess.is_set():reason='output_limit';break
            if time.perf_counter()-started>wall_seconds:reason='wall_time';break
            time.sleep(0.02)
        if reason:command(['kill',container],check=False,timeout=10)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();raise IsolationError('App container did not exit after termination.')
        for thread in readers:thread.join(timeout=2)
        writer.join(timeout=1)
        if excess.is_set():reason='output_limit'
        final=json.loads(command(['inspect',container,'--format','json']).stdout)[0]
        if final['State']['Running']:raise IsolationError('App container is still running.')
        stdout=bytes(streams['stdout']).decode('utf8',errors='replace')
        result=None
        if not final['State']['ExitCode'] and not reason:
            try:
                result=json.loads(stdout)
                if not isinstance(result,dict):result=None;reason='invalid_result_protocol'
            except ValueError:reason='invalid_result_protocol'
        return {'container_id':container,'image_id':pinned,'exit_code':final['State']['ExitCode'],'termination_reason':reason,
            'duration_ms':round((time.perf_counter()-started)*1000),'result':result,
            'stderr':bytes(streams['stderr']).decode('utf8',errors='replace'),
            'retained_stdout_bytes':len(streams['stdout']),'retained_stderr_bytes':len(streams['stderr']),
            'engine_policy':{'network':'none','host_mounts':[],'memory_bytes':MEMORY,'cpus':0.5,'user':'65534:65534','ulimits':LIMITS}}
    finally:
        try:
            if container:
                try:
                    removal=command(['remove','--force',container],check=False,timeout=15)
                    if removal.returncode:raise IsolationError('App run container cleanup failed.')
                except IsolationError:
                    command(['system','session','terminate'],check=False,timeout=15)
                    for proof in (PROOF,ROOT/'.runtime/code-isolation-verified.json'):
                        if proof.exists():proof.unlink()
                    raise IsolationError('Owned session stopped after app cleanup failed; restart and reverify before generation.')
        finally:
            if process:
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream and not stream.closed:stream.close()
