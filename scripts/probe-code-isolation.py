"""Hand-authored negative controls, executed only in native WSL containers."""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from projects.p06_code_assistant.sandbox import BOOTSTRAP,execute,image,command,verify_ready,IsolationError
from projects.p06_code_assistant.session import READY,STORAGE


def main():
    if '--ensure' in sys.argv:
        try:
            verify_ready();print('Current session/image/bootstrap isolation proof is valid.');return
        except IsolationError:pass
    # A failed or interrupted recheck must never leave an older passing marker active.
    proof_path=ROOT/'.runtime/code-isolation-verified.json'
    if proof_path.exists():proof_path.unlink()
    canary=ROOT/'.runtime/code-guard-canary/private.txt'
    canary.parent.mkdir(parents=True,exist_ok=True);canary.write_text('FICTIONAL HOST CANARY — never mounted',encoding='utf8')
    before=hashlib.sha256(canary.read_bytes()).hexdigest()
    cases=[]
    def check(name,code,condition,**limits):
        result=execute(code,[None],**limits)
        passed=bool(condition(result));cases.append({'id':name,'passed':passed,'result':result})
        print(name,'PASS' if passed else 'FAIL',result['duration_ms'],'ms',flush=True)
        (ROOT/'docs/code-isolation.json').write_text(json.dumps({'complete':False,'cases':cases},indent=2),encoding='utf8',newline='\n')
    check('function_runs','def solve(value): return 42',lambda r:r['exit_code']==0 and json.loads(r['stdout'])['outputs']==[42])
    check('host_files_unmapped', '''def solve(value):
    import os
    paths=["/mnt/c/Windows/win.ini","/mnt/d/genai-portfolio/.runtime/code-guard-canary/private.txt","/var/run/docker.sock"]
    return [os.path.exists(path) for path in paths]
''',lambda r:json.loads(r['stdout'])['outputs']==[[False,False,False]])
    check('file_writes_denied','''def solve(value):
    try:
        with open("/tmp/denied.txt","w") as target: target.write("blocked")
    except OSError as error: return error.errno
    return "write unexpectedly allowed"
''',lambda r:json.loads(r['stdout'])['outputs']==[27])
    check('network_unreachable','''def solve(value):
    import socket
    try:
        with socket.create_connection(("192.0.2.1",443),timeout=0.5): return "network unexpectedly allowed"
    except OSError as error: return error.errno
''',lambda r:json.loads(r['stdout'])['outputs']==[101])
    check('child_process_denied','''def solve(value):
    import subprocess
    try: subprocess.run(["/bin/true"],check=True)
    except OSError as error: return error.errno
    return "child unexpectedly allowed"
''',lambda r:json.loads(r['stdout'])['outputs']==[11])
    check('memory_limit','def solve(value): return len(bytearray(256*1024*1024))',lambda r:r['exit_code']!=0 and 'MemoryError' in r['stderr'])
    check('cpu_limit','def solve(value):\n    while True: pass',lambda r:r['exit_code']==137 and r['termination_reason'] is None)
    check('wall_limit','def solve(value):\n    import time\n    time.sleep(30)',lambda r:r['termination_reason']=='wall_time',wall_seconds=1.5)
    check('output_limit','def solve(value):\n    while True: print("x"*1024)',lambda r:r['termination_reason']=='output_limit' and len((r['stdout']+r['stderr']).encode())<=8192)
    unchanged=before==hashlib.sha256(canary.read_bytes()).hexdigest()
    assert unchanged
    output={'captured_at':datetime.now(timezone.utc).isoformat(),'complete':True,'passed':all(c['passed'] for c in cases),
            'mode':'actual native WSL OCI isolation; hand-authored controls; no model-generated code',
            'image_id':image(),'bootstrap_sha256':hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
            'creator_pid':json.loads(READY.read_text())['creator_pid'],'storage_path':str(STORAGE),
            'host_canary_unchanged':unchanged,'cases':cases,
            'limits_note':'runc receives setup address-space/thread limits; the trusted bootstrap lowers hard AS/nproc limits before candidate input. Swap cgroup support is unavailable, so the 128MB hard RLIMIT_AS supplements the memory cgroup.'}
    (ROOT/'docs/code-isolation.json').write_text(json.dumps(output,indent=2),encoding='utf8',newline='\n')
    assert output['passed'],'An isolation control failed; do not run model-generated code.'
    (ROOT/'.runtime/code-isolation-verified.json').write_text(json.dumps({k:output[k] for k in ['image_id','bootstrap_sha256','creator_pid','captured_at','passed']}),encoding='utf8')
    print('All nine isolation controls passed; model execution may now be enabled.')


if __name__=='__main__':main()
