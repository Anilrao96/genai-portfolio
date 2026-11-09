"""Actual app-specific toolchain and negative controls; no model-generated source."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from projects.p08_app_builder.runtime import PROOF,execute,image,ready,IsolationError
from projects.p06_code_assistant.session import READY

FRONTEND='export default function App(){return <main>Handwritten toolchain control</main>}'
BACKEND='from fastapi import FastAPI\napp=FastAPI()\n@app.get("/api/items")\nasync def items():return []\n'


def main():
    capture = ROOT / ('.runtime/app-isolation-probe.json' if '--ensure' in sys.argv else 'docs/app-isolation.json')
    if '--ensure' in sys.argv:
        try:ready();print('Current app image/session/toolchain proof is valid.');return
        except IsolationError:pass
    if PROOF.exists():PROOF.unlink()
    before=hashlib.sha256((ROOT/'.runtime/code-guard-canary/private.txt').read_bytes()).hexdigest()
    cases=[]
    def check(name,request,condition,**limits):
        result=execute(request,require_proof=False,**limits)
        passed=bool(condition(result));cases.append({'id':name,'passed':passed,'execution':result})
        print(name,'PASS' if passed else 'FAIL',result['duration_ms'],'ms',flush=True)
        capture.write_text(json.dumps({'complete':False,'cases':cases},indent=2),encoding='utf8',newline='\n')
        if not passed:raise AssertionError('App isolation control failed: '+name)
    check('kernel_file_network_process_memory',{'op':'controls'},lambda r:r['exit_code']==0 and r['result']['host_paths_absent']
        and r['result']['network_errno']==101 and r['result']['file_errno']==27 and r['result']['process_errno']==11 and r['result']['memory_refused'])
    check('real_react_build_and_asgi',{'op':'validate','files':{'backend.py':BACKEND,'App.jsx':FRONTEND},'requests':[{'method':'GET','path':'/api/items'}]},
        lambda r:r['exit_code']==0 and r['result']['build_passed'] and r['result']['responses']==[{'status':200,'body':[]}]
            and 100000<r['result']['bundle_bytes']<512000)
    # Bundle content is a trusted handwritten control artifact, not useful as checked-in evidence.
    cases[-1]['execution']['result'].pop('bundle_base64',None)
    check('cpu_limit',{'op':'cpu_control'},lambda r:r['exit_code']==137 and r['termination_reason'] is None)
    check('wall_limit',{'op':'wall_control'},lambda r:r['termination_reason']=='wall_time',wall_seconds=1.5)
    check('output_limit',{'op':'output_control'},lambda r:r['termination_reason']=='output_limit' and r['retained_stderr_bytes']<=16000)
    unchanged=before==hashlib.sha256((ROOT/'.runtime/code-guard-canary/private.txt').read_bytes()).hexdigest()
    assert unchanged
    marker=image()
    proof={'passed':True,'image_id':marker['image_id'],'context_sha256':marker['context_sha256'],
        'creator_pid':json.loads(READY.read_text())['creator_pid'],'verified_at':datetime.now(timezone.utc).isoformat()}
    evidence={'complete':True,'passed':True,'mode':'actual native container toolchain controls; handwritten sources, no model inference',
        **proof,'host_canary_unchanged':unchanged,'cases':cases,
        'memory_note':'Swap cgroup limit unavailable; generated backend has an additional hard 256MB address-space limit and one-process limit.'}
    capture.write_text(json.dumps(evidence,indent=2),encoding='utf8',newline='\n')
    PROOF.write_text(json.dumps(proof,indent=2),encoding='utf8',newline='\n')
    print('All app-specific controls passed; generated app execution may be enabled.')


if __name__=='__main__':main()
