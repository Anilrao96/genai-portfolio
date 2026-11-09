"""Actual backend, React and QA model roles plus isolated build/API checks. Browser acceptance is separate."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen2.5-coder:1.5b')
    args = parser.parse_args()
    spec = {'title': 'Reading Room', 'item_label': 'book',
            'brief': 'A calm reading list for fictional books. Add titles, mark books finished, and remove them.'}
    with httpx.Client(base_url='http://127.0.0.1:8108', timeout=600, trust_env=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert health.json()['generator'] == 'direct-source-v1', 'Restart the current app-builder service.'
        start = time.perf_counter()
        response = client.post('/api/build', json={'spec': spec, 'model': args.model})
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        response.raise_for_status()
        run = response.json()
        saved = client.get('/api/runs/' + run['id'])
        saved.raise_for_status()
        assert saved.json() == run, 'Saved build differs from HTTP response.'
    evidence={'captured_at':datetime.now(timezone.utc).isoformat(),'mode':'actual local HTTP build with backend/frontend/QA model roles and native OCI build/ASGI tests',
        'inference':'CPU; num_gpu=0; role-specific context and output token caps','complete':True,'passed':run['status']=='passed',
        'http_duration_ms': elapsed_ms, 'persisted_full_record_matches': True,
        'scope':'Core generation/build/API acceptance only; interactive browser preview remains separate.','run':run}
    (ROOT/'docs/app-builder-core-live.json').write_text(json.dumps(evidence,indent=2),encoding='utf8',newline='\n')
    print(json.dumps({'status':run['status'],'run_id':run['id'],'model_calls':run['model_calls'],'build_attempts':run['build_attempts'],
        'tests_passed':run.get('tests_passed'),'tests_total':run.get('tests_total'),'duration_ms':run['duration_ms'],'error':run['error']},indent=2))
    if run['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
