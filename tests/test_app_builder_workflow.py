import asyncio
import base64
import hashlib

from fastapi.testclient import TestClient

from projects.p08_app_builder.app import create_app as create_builder
from projects.p08_app_builder.builder import AppBuilder
from projects.p08_app_builder.contracts import AppSpec
from projects.p08_app_builder.preview import create_app as create_preview
from projects.p08_app_builder.qa import CORE, extra_cases
from projects.p08_app_builder.runtime import IsolationError
from projects.p08_app_builder.store import BuildStore


SPEC = AppSpec(title='Reading Room', item_label='book', brief='Track fictional books to read and mark them finished.')
SCENARIOS = ['long_title', 'missing_title']
BACKEND = 'from fastapi import FastAPI\napp = FastAPI()\n'
FRONTEND = 'export default function App(){return null}'


class FixtureRole:
    def __init__(self, source):
        self.source = source
        self.feedback = []

    async def generate(self, spec, previous='', feedback=None):
        self.feedback.append(feedback)
        return {'code': self.source, 'note': 'Offline fixture'}, {}

    async def review(self, spec, files, tests):
        return {'approved': True, 'findings': ['Offline fixture'], 'scenarios': SCENARIOS}, {}


def test_backend_repair_receives_isolated_route_failure_and_qa_runs(tmp_path):
    backend, frontend = FixtureRole(BACKEND), FixtureRole(FRONTEND)
    calls = []

    def execute(request):
        calls.append(request['op'])
        if len(calls) == 1:
            return {'exit_code': 0, 'result': {'build_passed': False, 'stage': 'backend_contract', 'error': 'Sync routes: /api/items'}}
        cases = CORE if request['op'] == 'validate' else CORE + extra_cases(SCENARIOS)
        assert request['requests'] == [case[0] for case in cases]
        return {'exit_code': 0, 'result': {'build_passed': True, 'responses': [case[1] for case in cases],
                                           'bundle_base64': base64.b64encode(b'fixture').decode()}}

    store = BuildStore(tmp_path)
    result = asyncio.run(AppBuilder(backend, frontend, FixtureRole(''), store, execute, lambda: {}).run(SPEC, 'fixture'))
    assert result['status'] == 'passed'
    assert result['build_attempts'] == 2
    assert backend.feedback[1]['build_error'] == 'Sync routes: /api/items'
    assert frontend.feedback == [None]
    assert calls == ['validate', 'validate', 'backend_request']
    assert result['tests_passed'] == len(CORE) + 2
    assert store.get(result['id'])['bundle_sha256'] == hashlib.sha256(b'fixture').hexdigest()


def saved_build(store):
    run_id = 'a' * 32
    workspace = store.workspace(run_id)
    workspace.write('backend.py', BACKEND)
    workspace.write('App.jsx', FRONTEND)
    (workspace.path / 'app.js').write_bytes(b'fixture')
    store.save({'id': run_id, 'status': 'passed', 'spec': SPEC.model_dump(), 'manifest': workspace.manifest(SPEC),
                'bundle_sha256': hashlib.sha256(b'fixture').hexdigest()})
    return f'/r/{run_id}', workspace


def test_preview_replays_state_and_refuses_changed_source(tmp_path):
    store = BuildStore(tmp_path)
    route, workspace = saved_build(store)
    calls = []

    def execute(request):
        calls.append(request)
        record = {'id': 1, 'title': 'Cedar', 'done': False}
        responses = [{'status': 200, 'body': []}, {'status': 201, 'body': record}, {'status': 200, 'body': [record]}]
        return {'exit_code': 0, 'duration_ms': 1, 'result': {'responses': responses[:len(request['requests'])]}}

    client = TestClient(create_preview(store, execute), base_url='http://127.0.0.1:8118')
    assert client.get(route + '/api/items').json() == []
    assert client.post(route + '/api/items', json={'title': 'Cedar'}).status_code == 201
    assert client.get(route + '/api/items').json()[0]['title'] == 'Cedar'
    assert [call['method'] for call in calls[-1]['requests']] == ['GET', 'POST', 'GET']
    assert client.post(route + '/reset').status_code == 200
    assert client.get(route + '/api/items').json() == []
    workspace.write('backend.py', BACKEND + '# changed')
    assert client.get(route + '/api/items').status_code == 409
    assert len(calls) == 4


def test_preview_rejects_changed_prefix_and_cross_origin(tmp_path):
    store = BuildStore(tmp_path)
    route, _ = saved_build(store)

    def execute(request):
        count = len(request['requests'])
        return {'exit_code': 0, 'duration_ms': 1, 'result': {'responses': [{'status': 200, 'body': [count]}] * count}}

    client = TestClient(create_preview(store, execute), base_url='http://127.0.0.1:8118')
    assert client.get(route + '/api/items').json() == [1]
    assert client.get(route + '/api/items').status_code == 409
    assert client.post(route + '/reset', headers={'Origin': 'http://127.0.0.1:8108'}).status_code == 403
    assert client.post(route + '/api/items', content='{"title": NaN}').status_code == 422


def test_build_api_blocks_missing_isolation_before_roles(tmp_path):
    def blocked():
        raise IsolationError('Run the isolation probe first.')

    client = TestClient(create_builder(BuildStore(tmp_path), guard=blocked), base_url='http://127.0.0.1:8108')
    response = client.post('/api/build', json={'spec': SPEC.model_dump(), 'model': 'fixture'})
    assert response.status_code == 503
    assert response.json()['detail'] == 'Run the isolation probe first.'
    assert client.get('/api/runs').json()['runs'] == []
