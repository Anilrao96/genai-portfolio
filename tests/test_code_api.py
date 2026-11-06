from fastapi.testclient import TestClient

from projects.p06_code_assistant.app import create_app
from projects.p06_code_assistant.runs import RunStore
from test_code_assistant import FixtureModel,FixtureSandbox,response


class Catalog:
    async def models(self):return [{'name':'fixture','capabilities':['completion']},{'name':'embed','capabilities':['embedding']}]


def client(tmp_path,sandbox=None):
    return TestClient(create_app(RunStore(tmp_path/'runs'),lambda model:FixtureModel(),sandbox or FixtureSandbox(),Catalog()),base_url='http://127.0.0.1')


def test_api_runs_real_graph_with_labeled_fixtures_and_saves_history(tmp_path):
    api=client(tmp_path,FixtureSandbox([response(error='ZeroDivisionError',exit_code=1),response([0,4,0,1.5])]))
    assert api.get('/health').json()['execution_protocol']=='verified-wsl-oci-v1'
    assert len(api.get('/api/tasks').json()['tasks'])==2
    assert len(api.get('/api/models').json()['models'])==1
    result=api.post('/api/run',json={'task_id':'mean','model':'fixture','starting_code':'def solve(data): return sum(data)/len(data)'}).json()
    assert result['status']=='passed' and result['executions']==2
    assert api.get('/api/runs/'+result['id']).json()['attempts'][0]['feedback']=='ZeroDivisionError'
    assert api.get('/api/runs').json()['runs'][0]['id']==result['id']


def test_unverified_runtime_blocks_execution(tmp_path):
    api=client(tmp_path,FixtureSandbox(ready=False))
    assert api.get('/api/runtime').json()['ready'] is False
    assert api.post('/api/run',json={'task_id':'mean','model':'fixture'}).status_code==503
    assert api.get('/api/runs').json()=={'runs':[]}


def test_http_and_input_boundaries(tmp_path):
    api=client(tmp_path)
    payload={'task_id':'mean','model':'fixture'}
    assert api.post('/api/run',json=payload,headers={'Origin':'https://other.example'}).status_code==403
    assert api.post('/api/run',content='x'*32001).status_code==413
    assert api.get('/',headers={'Host':'other.example'}).status_code==400
    for extra in ({'task_id':'other'},{'model':'a;b'},{'starting_code':'x'*6001},{'starting_code':'🌲'*1600},{'extra':1}):
        assert api.post('/api/run',json={**payload,**extra}).status_code==422
    assert api.post('/api/run',json={**payload,'model':'embed'}).status_code==422
    assert api.get('/api/runs/not-an-id').status_code==404
    assert api.get('/').headers['cache-control']=='no-store'
