import asyncio
import json

import pytest

from projects.p06_code_assistant.assistant import Candidate,CodeAssistant,equal
from projects.p06_code_assistant.runs import RunStore
from projects.p06_code_assistant.sandbox import IsolationError,MEMORY,ULIMITS,verify_inspection


def inspected():
    return {'Image':'sha256:'+'a'*64,'Config':{'User':'65534:65534','Labels':{'portfolio.project':'p06_code_assistant'},'Healthcheck':{'Test':['NONE']}},
            'HostConfig':{'NetworkMode':'none','Memory':MEMORY,'NanoCpus':500_000_000,'Ulimits':[{'Name':k,'Soft':v,'Hard':v} for k,v in ULIMITS.items()]},'Mounts':[],'Ports':{}}


def test_engine_policy_matches_expected_kernel_boundary():
    data=inspected();verify_inspection(data,data['Image'])


@pytest.mark.parametrize('change',['network','memory','user','mount','image','limits','labels','health','ports'])
def test_policy_mismatch_refuses_start(change):
    data=inspected()
    if change=='network':data['HostConfig']['NetworkMode']='bridge'
    elif change=='memory':data['HostConfig']['Memory']=0
    elif change=='user':data['Config']['User']='0'
    elif change=='mount':data['Mounts']=[{'Source':'D:/'}]
    elif change=='image':data['Image']='sha256:'+'b'*64
    elif change=='limits':data['HostConfig']['Ulimits']=[]
    elif change=='labels':data['Config']['Labels']={}
    elif change=='health':data['Config']['Healthcheck']={'Test':['CMD','curl']}
    else:data['Ports']={'80/tcp':[{'HostPort':'80'}]}
    with pytest.raises(IsolationError):verify_inspection(data,'sha256:'+'a'*64)


class FixtureSandbox:
    def __init__(self,responses=None,ready=True):self.responses=list(responses or []);self.calls=0;self.is_ready=ready
    def ready(self):
        if not self.is_ready:raise IsolationError('Fixture isolation unavailable.')
    def run(self,code,inputs):
        self.calls+=1
        return self.responses.pop(0)


def response(outputs=None,error='',exit_code=0,reason=None):
    return {'stdout':json.dumps({'outputs':outputs}), 'stderr':error,'exit_code':exit_code,'termination_reason':reason,
            'mode':'offline fixture; code was not executed'}


class FixtureModel:
    def __init__(self,code='def solve(data): return 0'):self.calls=0;self.code=code;self.contexts=[]
    async def propose(self,context):
        self.calls+=1;self.contexts.append(context)
        return Candidate(code=self.code,note='Offline fixture; no model call.'),{}


def test_actual_langgraph_failing_sample_routes_through_repair(tmp_path):
    store=RunStore(tmp_path/'runs');model=FixtureModel()
    sandbox=FixtureSandbox([response(error='ZeroDivisionError: division by zero',exit_code=1),response([0,4,0,1.5])])
    result=asyncio.run(CodeAssistant(model,store,sandbox).run('mean','fixture','def solve(data): return sum(data)/len(data)'))
    assert result['status']=='passed' and result['executions']==2 and result['model_calls']==1
    assert [e['stage'] for e in result['trace']]==['execute','repair','execute']
    assert 'ZeroDivisionError' in model.contexts[0]['feedback']
    assert store.get(result['id'])['attempts'][1]['tests_passed']==4
    assert store.history()[0]['id']==result['id']


def test_generation_then_wrong_output_is_bounded(tmp_path):
    model=FixtureModel();sandbox=FixtureSandbox([response([99]*4) for _ in range(3)])
    result=asyncio.run(CodeAssistant(model,RunStore(tmp_path/'runs'),sandbox).run('mean','fixture'))
    assert result['status']=='failed' and result['executions']==3 and result['model_calls']==3
    assert [e['stage'] for e in result['trace']]==['generate','execute','repair','execute','repair','execute']
    assert json.loads(model.contexts[1]['feedback'])['expected']==0


@pytest.mark.parametrize('execution',[response(reason='wall_time',exit_code=137),response(reason='output_limit',exit_code=137),response(exit_code=137)])
def test_resource_limits_stop_without_model_retry(tmp_path,execution):
    model=FixtureModel();sandbox=FixtureSandbox([execution])
    result=asyncio.run(CodeAssistant(model,RunStore(tmp_path/'runs'),sandbox).run('mean','fixture','def solve(data): return data'))
    assert result['status']=='limited' and result['executions']==1 and model.calls==0


def test_isolation_missing_refuses_even_model_generation(tmp_path):
    model=FixtureModel();sandbox=FixtureSandbox(ready=False)
    with pytest.raises(IsolationError):asyncio.run(CodeAssistant(model,RunStore(tmp_path/'runs'),sandbox).run('mean','fixture'))
    assert model.calls==0 and sandbox.calls==0


def test_syntax_failure_is_not_executed_on_host(tmp_path):
    model=FixtureModel();sandbox=FixtureSandbox([response([0,4,0,1.5])])
    result=asyncio.run(CodeAssistant(model,RunStore(tmp_path/'runs'),sandbox).run('mean','fixture','def solve(:'))
    assert result['status']=='passed' and sandbox.calls==1 and result['executions']==2
    assert result['attempts'][0]['execution'] is None


def test_boolean_is_not_an_accepted_numeric_result_and_paths_stay_scoped(tmp_path):
    assert not equal(True,1) and equal(0,0.0) and not equal([True],[1])
    with pytest.raises(ValueError):RunStore('D:/outside-code-runs')
    store=RunStore(tmp_path/'runs')
    with pytest.raises(ValueError):store.get('../../elsewhere')
