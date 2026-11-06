"""Fresh fictional QA store: actual model repair, cached extraction, quarantine/replay and rollback."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from projects.p05_self_healing_pipeline.store import Store, runtime_path


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8105')
    parser.add_argument('--state-path',required=True)
    parser.add_argument('--model',default='qwen3:4b')
    args=parser.parse_args()
    store=Store(runtime_path(args.state_path))
    cases=[]
    with httpx.Client(base_url=args.base_url,timeout=200,trust_env=False) as client:
        assert client.get('/health').json()['contract']=='orders-v1'
        assert not client.get('/api/history').json()['batches'],'Use a fresh dedicated QA database; keep prior attempts as evidence.'
        assert not store.history()['batches'],'The supplied QA path must match the running API and be fresh.'
        samples=client.get('/api/config').json()['samples']
        def ingest(name,source,check,parent=None):
            url='/api/ingest' if parent is None else f'/api/batches/{parent}/replay'
            started=time.perf_counter()
            response=client.post(url,json={'csv_text':source,'date_style':'month_first','model':args.model})
            response.raise_for_status(); result=response.json()
            elapsed=round((time.perf_counter()-started)*1000)
            passed=bool(check(result));cases.append({'id':name,'passed':passed,'http_elapsed_ms':elapsed,'response':result})
            (ROOT/'docs/pipeline-live.json').write_text(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(),
                'mode':'partial actual live capture; inspect failed/incomplete checks','model':args.model,
                'complete':False,'cases':cases},indent=2),encoding='utf8',newline='\n')
            print(name,'PASS' if passed else 'FAIL',elapsed,'HTTP ms',flush=True)
            return result
        clean=ingest('standard_batch',samples['baseline'],lambda r:r['status']=='committed' and r['model_calls_this_request']==0)
        healed=ingest('model_healed',samples['drifted'],lambda r:r['status']=='committed' and r['plan_origin']=='model' and 1<=r['model_calls_this_request']<=2 and r['after']['valid_rows']==2)
        state=client.get('/api/snapshot').json()
        assert state['totals']=={'orders':4,'units':8,'revenue_cents':252485}
        repeated=ingest('idempotent_input',samples['drifted'],lambda r:r.get('idempotent_replay') and r['model_calls_this_request']==0)
        assert client.get('/api/snapshot').json()==state
        cached=ingest('learned_extractor',samples['drifted'].replace('ORD-200','ORD-210'),lambda r:r['status']=='committed' and r['plan_origin']=='cached' and r['model_calls_this_request']==0)
        assert cached['extractor_learned_from']==healed['batch_id']
        before_bad=client.get('/api/snapshot').json()
        bad=ingest('invalid_value_quarantined',samples['quarantine'],lambda r:r['status']=='quarantined' and r['model_calls_this_request']<=2)
        assert client.get('/api/snapshot').json()==before_bad
        parent=client.get('/api/batches/'+bad['batch_id']).json()
        replay=ingest('corrected_source_replay',samples['quarantine'].replace(',0.0,',',2.0,'),lambda r:r['status']=='committed' and r['plan_origin']=='cached',bad['batch_id'])
        child=client.get('/api/batches/'+replay['batch_id']).json()
        assert child['replay_of']==bad['batch_id'] and child['source_sha']!=parent['source_sha']
        assert replay['extractor_learned_from']==healed['batch_id']
        assert client.get('/api/batches/'+bad['batch_id']).json()['source']==parent['source']
        after_replay=client.get('/api/snapshot').json()
        assert after_replay['totals']=={'orders':7,'units':15,'revenue_cents':500170}
        unknown=ingest('unknown_schema_quarantined',samples['drifted'].replace('Buyer','Unreviewed field'),lambda r:r['status']=='quarantined' and r['model_calls_this_request']==0)
        assert client.get('/api/snapshot').json()==after_replay
        rollback=client.post('/api/rollback',json={'target_revision':clean['committed_revision'],'expected_active_revision':after_replay['active_revision']})
        rollback.raise_for_status();assert rollback.json()['totals']=={'orders':2,'units':3,'revenue_cents':6500}
        stale=client.post('/api/rollback',json={'target_revision':0,'expected_active_revision':after_replay['active_revision']})
        assert stale.status_code==409
        restore=client.post('/api/rollback',json={'target_revision':after_replay['active_revision'],'expected_active_revision':clean['committed_revision']})
        restore.raise_for_status();assert client.get('/api/snapshot').json()==after_replay
        # A separate SQLite connection verifies what the API actually persisted.
        assert store.snapshot()==after_replay
        persisted_parent=store.batch(bad['batch_id'])
        assert persisted_parent['source_sha']==hashlib.sha256(samples['quarantine'].encode()).hexdigest()
        output={'captured_at':datetime.now(timezone.utc).isoformat(),'mode':'actual local-model CSV extraction + real SQLite snapshots',
                'model':args.model,'inference':'CPU; LOCAL_AI_NUM_GPU=0','cases':cases,'complete':True,'passed':all(c['passed'] for c in cases),
                'rollback':rollback.json(),'stale_rollback_status':stale.status_code,'restore':restore.json(),
                'raw_quarantine_source_unchanged':True,'separate_connection_persistence':True,
                'cached_extractor_original_lineage_preserved':True,
                'duration_note':'http_elapsed_ms measures this HTTP request; an idempotent response retains its original batch duration_ms and trace, with zero model_calls_this_request.',
                'final_snapshot':after_replay,'final_snapshot_sha256':digest(after_replay['records'])}
        (ROOT/'docs/pipeline-live.json').write_text(json.dumps(output,indent=2),encoding='utf8',newline='\n')
        assert output['passed'],'Inspect docs/pipeline-live.json; no unverified result is complete.'


if __name__=='__main__':main()
