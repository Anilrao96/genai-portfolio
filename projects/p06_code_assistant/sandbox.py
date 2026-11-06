"""Native WSL OCI containers. Inspect policy before start; never run candidate code on Windows."""
import json
import os
import re
import subprocess
import threading
import time
import uuid
import hashlib

from .session import CLI,READY,ROOT,SESSION,STORAGE

IMAGE_FILE=ROOT/'.runtime/code-image.json'
MEMORY=128*1024*1024
ULIMITS={'cpu':2,'as':2*1024**3,'fsize':0,'nproc':16,'nofile':128}


class IsolationError(RuntimeError):pass


# Trusted bootstrap runs inside the container before loading any candidate source.
BOOTSTRAP='''import ctypes,json,os,resource,sys,traceback
libc=ctypes.CDLL(None)
if libc.prctl(38,1,0,0,0)!=0:raise RuntimeError("Cannot set no-new-privileges")
# runc needs setup address space/threads. Lower hard limits before reading candidate input.
resource.setrlimit(resource.RLIMIT_AS,(134217728,134217728))
resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
limits={"cpu":resource.getrlimit(resource.RLIMIT_CPU),"as":resource.getrlimit(resource.RLIMIT_AS),"fsize":resource.getrlimit(resource.RLIMIT_FSIZE),"nproc":resource.getrlimit(resource.RLIMIT_NPROC),"nofile":resource.getrlimit(resource.RLIMIT_NOFILE)}
required={"cpu":2,"as":134217728,"fsize":0,"nproc":1,"nofile":128}
status=open("/proc/self/status").read()
interfaces=os.listdir("/sys/class/net")
if os.getuid()!=65534 or any(tuple(limits[k])!=(v,v) for k,v in required.items()) or "CapEff:\\t0000000000000000" not in status or "NoNewPrivs:\\t1" not in status or interfaces!=["lo"]:
    raise RuntimeError("Container kernel policy verification failed")
print("ISOLATION_POLICY="+json.dumps({"uid":os.getuid(),"limits":limits,"interfaces":interfaces,"capabilities_effective":0,"no_new_privileges":True}),file=sys.stderr,flush=True)
request=json.load(sys.stdin)
try:
    scope={}
    exec(compile(request["code"],"<candidate>","exec"),scope)
    outputs=[scope["solve"](value) for value in request["inputs"]]
    print(json.dumps({"outputs":outputs},allow_nan=False),flush=True)
except BaseException:
    traceback.print_exc(limit=8)
    sys.exit(1)
'''


def command(args,timeout=20,check=True):
    env={**os.environ,'TEMP':str(ROOT/'.runtime/temp'),'TMP':str(ROOT/'.runtime/temp')}
    try:
        result=subprocess.run([str(CLI),'--session',SESSION,*args],cwd=ROOT,env=env,capture_output=True,timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise IsolationError('Native container command timed out: '+args[0]) from exc
    if check and result.returncode:
        raise IsolationError(result.stderr.decode('utf8',errors='replace')[:600] or 'Native container command failed.')
    return result


def image():
    if not CLI.is_file() or not READY.is_file() or not IMAGE_FILE.is_file():
        raise IsolationError('Container runtime is not ready. Run scripts/Setup-CodeAssistant.ps1.')
    ready=json.loads(READY.read_text())
    if ready['session']!=SESSION or ready['storage_path']!=str(STORAGE) or not (STORAGE/'storage.vhdx').is_file():
        raise IsolationError('Project-local container storage could not be verified.')
    value=json.loads(IMAGE_FILE.read_text())['image_id']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',value):raise IsolationError('Invalid pinned image ID.')
    return value


def verify_ready():
    pinned=image()
    path=ROOT/'.runtime/code-isolation-verified.json'
    if not path.is_file():raise IsolationError('Isolation controls have not passed. Run scripts/probe-code-isolation.py.')
    proof=json.loads(path.read_text())
    if (not proof.get('passed') or proof.get('image_id')!=pinned
        or proof.get('bootstrap_sha256')!=hashlib.sha256(BOOTSTRAP.encode()).hexdigest()
        or proof.get('creator_pid')!=json.loads(READY.read_text())['creator_pid']):
        raise IsolationError('Isolation proof is stale for this image, bootstrap or session. Rerun the isolation probe.')
    listing=command(['system','session','list','--verbose']).stdout.decode('utf8',errors='replace')
    if not re.search(rf'^\S+\s+{proof["creator_pid"]}\s+{re.escape(SESSION)}\s*$',listing,re.M):
        raise IsolationError('The verified project session is no longer active. Restart and verify it.')
    return proof


class VerifiedSandbox:
    def ready(self):return verify_ready()
    def run(self,code,inputs):
        verify_ready()
        return execute(code,inputs)


def verify_inspection(data,image_id):
    host=data['HostConfig'];config=data['Config']
    actual={item['Name']:(item['Soft'],item['Hard']) for item in host.get('Ulimits',[])}
    health=config.get('Healthcheck')
    if (data['Image']!=image_id or config['User']!='65534:65534' or host.get('NetworkMode')!='none'
        or host.get('Memory')!=MEMORY or host.get('NanoCpus')!=500_000_000
        or data.get('Mounts') or data.get('Ports') or (health and health.get('Test')!=['NONE'])
        or any(actual.get(k)!=(v,v) for k,v in ULIMITS.items())
        or config.get('Labels',{}).get('portfolio.project')!='p06_code_assistant'):
        raise IsolationError('Engine policy mismatch: '+json.dumps({'image':data['Image'],'user':config['User'],'host':host,'mounts':data.get('Mounts'),'labels':config.get('Labels'),'health':health})[:1600])


def execute(code,inputs,wall_seconds=6.0,output_bytes=8192):
    if not isinstance(code,str) or not 1<=len(code.encode('utf8'))<=6000:
        raise IsolationError('Candidate source must be 1–6,000 UTF-8 bytes.')
    payload=json.dumps({'code':code,'inputs':inputs},allow_nan=False).encode('utf8')
    if len(payload)>16000 or not 0.5<=wall_seconds<=6 or not 1024<=output_bytes<=8192:
        raise IsolationError('Input or execution bounds exceeded.')
    pinned=image();name='portfolio-code-'+uuid.uuid4().hex;container_id=None;process=None
    args=['create','--interactive','--name',name,'--label','portfolio.project=p06_code_assistant',
          '--network','none','--user','65534:65534','--memory','128m','--cpus','0.5','--no-healthcheck','--pull','never']
    for key,value in ULIMITS.items():args+=['--ulimit',f'{key}={value}:{value}']
    args += [pinned,'python','-I','-B','-c',BOOTSTRAP]
    try:
        created=command(args)
        candidate=created.stdout.decode('utf8').strip()
        if not re.fullmatch(r'[0-9a-f]{64}',candidate):raise IsolationError('Unexpected container identifier.')
        container_id=candidate
        inspection=json.loads(command(['inspect',container_id,'--format','json']).stdout)[0]
        verify_inspection(inspection,pinned)
        process=subprocess.Popen([str(CLI),'--session',SESSION,'start','--attach','--interactive',container_id],
            cwd=ROOT,env={**os.environ,'TEMP':str(ROOT/'.runtime/temp'),'TMP':str(ROOT/'.runtime/temp')},
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        buffers={'stdout':bytearray(),'stderr':bytearray()};lock=threading.Lock();reason=None;total=0;excess=threading.Event()
        def read(stream,key):
            nonlocal total
            while data:=stream.read1(4096):
                with lock:
                    # Reserve space in each stream for the trusted stderr policy line.
                    remaining=max(0,output_bytes//2-len(buffers[key]))
                    buffers[key].extend(data[:remaining]);total+=len(data)
                    if len(data)>remaining:excess.set()
                    # Keep draining discarded bytes: a blocked attach stream can stall control RPCs.
        def write():
            try:process.stdin.write(payload);process.stdin.close()
            except (OSError,BrokenPipeError):pass
        readers=[threading.Thread(target=read,args=(process.stdout,'stdout'),daemon=True),threading.Thread(target=read,args=(process.stderr,'stderr'),daemon=True)]
        for thread in readers:thread.start()
        writer=threading.Thread(target=write,daemon=True);writer.start();started=time.perf_counter()
        while process.poll() is None:
            if excess.is_set():reason='output_limit';break
            if time.perf_counter()-started>wall_seconds:reason='wall_time';break
            time.sleep(0.02)
        if reason:command(['kill',container_id],timeout=10,check=False)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();raise IsolationError('Container attach did not exit after termination.')
        for thread in readers:thread.join(timeout=2)
        writer.join(timeout=1)
        if excess.is_set():reason='output_limit'
        final=json.loads(command(['inspect',container_id,'--format','json']).stdout)[0]
        if final['State']['Running']:raise IsolationError('Container failed to stop.')
        stderr=bytes(buffers['stderr']).decode('utf8',errors='replace')
        policy_line=next((line for line in stderr.splitlines() if line.startswith('ISOLATION_POLICY=')),None)
        policy=json.loads(policy_line.split('=',1)[1]) if policy_line else None
        if policy is None:
            raise IsolationError('Trusted in-container policy check did not complete: '+stderr[:500])
        return {'container_id':container_id,'image_id':pinned,'exit_code':final['State']['ExitCode'],
                'termination_reason':reason,'stdout':bytes(buffers['stdout']).decode('utf8',errors='replace'),
                'stderr':'\n'.join(line for line in stderr.splitlines() if not line.startswith('ISOLATION_POLICY=')),
                'duration_ms':round((time.perf_counter()-started)*1000),'kernel_policy':policy,
                'engine_policy':{'memory_bytes':MEMORY,'cpus':0.5,'network':'none','user':'65534:65534','host_mounts':[],
                                 'ulimits':ULIMITS,'storage_path':str(STORAGE)},
                'wall_seconds':wall_seconds,'output_bytes':output_bytes}
    finally:
        try:
            if container_id:
                try:
                    removed=command(['remove','--force',container_id],timeout=15,check=False)
                    if removed.returncode:raise IsolationError('Could not remove the run container.')
                except IsolationError:
                    # Terminate only this project's session if the per-container control path failed.
                    command(['system','session','terminate'],timeout=15,check=False)
                    proof=ROOT/'.runtime/code-isolation-verified.json'
                    if proof.exists():proof.unlink()
                    raise IsolationError('Owned runtime session stopped after cleanup failure; restart and verify isolation before another run.')
        finally:
            if process:
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream and not stream.closed:stream.close()
