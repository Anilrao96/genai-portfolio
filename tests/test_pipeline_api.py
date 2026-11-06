from fastapi.testclient import TestClient

from projects.p05_self_healing_pipeline.app import create_app
from projects.p05_self_healing_pipeline.store import Store
from test_pipeline_engine import Planner, sample


class Catalog:
    async def models(self):return [{"name":"fixture","capabilities":["completion"]},{"name":"embed","capabilities":["embedding"]}]


def client(tmp_path):
    return TestClient(create_app(Store(tmp_path/"audit.sqlite3"),lambda model:Planner(),Catalog()),base_url="http://127.0.0.1")


def test_api_heals_and_retains_sources_snapshots_and_history(tmp_path):
    api=client(tmp_path)
    assert api.get('/health').json()['contract']=='orders-v1'
    assert len(api.get('/api/config').json()['samples'])==3
    assert len(api.get('/api/models').json()['models'])==1
    result=api.post('/api/ingest',json={'csv_text':sample('drifted'),'model':'fixture'}).json()
    assert result['status']=='committed' and result['model_calls']==1
    assert api.get('/api/snapshot').json()['totals']['revenue_cents']==245985
    saved=api.get('/api/batches/'+result['batch_id']).json()
    assert saved['source']==sample('drifted') and saved['events'][-1]['operation']=='committed'
    assert api.get('/api/history').json()['batches'][0]['status']=='committed'
    rollback=api.post('/api/rollback',json={'target_revision':0,'expected_active_revision':result['committed_revision']})
    assert rollback.status_code==200 and rollback.json()['totals']['orders']==0
    assert api.post('/api/rollback',json={'target_revision':0,'expected_active_revision':result['committed_revision']}).status_code==409


def test_api_boundaries_and_invalid_input(tmp_path):
    api=client(tmp_path)
    payload={'csv_text':sample('baseline')}
    assert api.post('/api/ingest',json=payload,headers={'Origin':'https://other.example'}).status_code==403
    assert api.post('/api/ingest',content='x'*65001).status_code==413
    assert api.get('/',headers={'Host':'other.example'}).status_code==400
    for change in ({'date_style':'guess'},{'csv_text':'x'*32001},{'model':'a;b'},{'extra':1}):
        assert api.post('/api/ingest',json={**payload,**change}).status_code==422
    assert api.get('/api/batches/nope').status_code==404
    assert api.post('/api/batches/'+'0'*32+'/replay',json=payload).status_code==404
    assert api.post('/api/rollback',json={'target_revision':True,'expected_active_revision':0}).status_code==422
    assert api.get('/').headers['cache-control']=='no-store'


def test_malformed_source_is_saved_in_quarantine(tmp_path):
    api=client(tmp_path)
    result=api.post('/api/ingest',json={'csv_text':'a,b\n1'}).json()
    assert result['status']=='quarantined' and result['model_calls']==0
    assert api.get('/api/batches/'+result['batch_id']).json()['source']=='a,b\n1'
    assert api.get('/api/snapshot').json()['active_revision']==0
