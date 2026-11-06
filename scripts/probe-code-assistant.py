"""Actual HTTP model workflows and a zero-model wall-limit stop in the verified runtime."""
from datetime import datetime,timezone
import json
from pathlib import Path
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    cases=[]
    with httpx.Client(base_url='http://127.0.0.1:8106',timeout=260,trust_env=False) as client:
        assert client.get('/health').json()['execution_protocol']=='verified-wsl-oci-v1'
        assert client.get('/api/runtime').json()['ready']
        tasks={task['id']:task for task in client.get('/api/tasks').json()['tasks']}
        for case_id,task,code in [('repair_mean','mean',tasks['mean']['starting_code']),('generate_words','words',''),
                                 ('wall_limit_no_retry','mean','def solve(data):\n    import time\n    time.sleep(30)')]:
            started=time.perf_counter()
            response=client.post('/api/run',json={'task_id':task,'starting_code':code,'model':'qwen3:4b'})
            response.raise_for_status();run=response.json()
            if case_id=='wall_limit_no_retry':passed=run['status']=='limited' and run['model_calls']==0 and run['executions']==1
            else:
                passed=run['status']=='passed' and 1<=run['model_calls']<=3 and all(a['execution']['engine_policy']['network']=='none' for a in run['attempts'] if a['execution'])
                if case_id=='repair_mean':passed=passed and run['executions']>=2 and not run['attempts'][0]['passed'] and 'ZeroDivisionError' in run['attempts'][0]['feedback']
            saved=client.get('/api/runs/'+run['id']).json()
            assert saved==run,'Persisted run differs from HTTP response.'
            cases.append({'id':case_id,'passed':bool(passed),'http_elapsed_ms':round((time.perf_counter()-started)*1000),'response':run})
            evidence={'captured_at':datetime.now(timezone.utc).isoformat(),'mode':'actual local-model HTTP workflows + native container resource control',
                      'model':'qwen3:4b','inference':'CPU; LOCAL_AI_NUM_GPU=0','complete':len(cases)==3,'passed':all(case['passed'] for case in cases),
                      'cases':cases,'persistent_history_verified':True}
            (ROOT/'docs/code-assistant-live.json').write_text(json.dumps(evidence,indent=2),encoding='utf8',newline='\n')
            print(case_id,'PASS' if passed else 'FAIL',run['model_calls'],'model calls',run['executions'],'executions',run['duration_ms'],'ms',flush=True)
    assert evidence['complete'] and evidence['passed'],'Inspect the preserved live capture.'


if __name__=='__main__':main()
