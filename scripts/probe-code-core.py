"""Real local-model generate/repair workflows, only through the verified container boundary."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from projects.p06_code_assistant.assistant import CodeAssistant,CodeModel
from projects.p06_code_assistant.runs import RunStore
from projects.p06_code_assistant.tasks import TASKS


async def main():
    cases=[];store=RunStore(ROOT/'.runtime/code-qa/runs')
    assistant=CodeAssistant(CodeModel('qwen3:4b'),store)
    for name,task,source in [('repair_mean','mean',TASKS['mean']['starting_code']),('generate_words','words','')]:
        run=await assistant.run(task,'qwen3:4b',source)
        passed=run['status']=='passed' and 1<=run['model_calls']<=3 and 1<=run['executions']<=3
        if name=='repair_mean':passed=passed and run['executions']>=2 and not run['attempts'][0]['passed']
        cases.append({'id':name,'passed':passed,'response':run})
        data={'captured_at':datetime.now(timezone.utc).isoformat(),'mode':'actual Qwen3 CPU + native WSL OCI containers',
              'model':'qwen3:4b','complete':len(cases)==2,'passed':all(case['passed'] for case in cases),'cases':cases,
              'scope':'Core workflow only; HTTP/browser acceptance remains separate.'}
        (ROOT/'docs/code-core-live.json').write_text(json.dumps(data,indent=2),encoding='utf8',newline='\n')
        print(name,'PASS' if passed else 'FAIL',run['model_calls'],'model calls',run['executions'],'executions',run['duration_ms'],'ms',flush=True)
    assert all(case['passed'] for case in cases),'Inspect the captured runs; failed cases are preserved.'


if __name__=='__main__':asyncio.run(main())
