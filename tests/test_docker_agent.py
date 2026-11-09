import sqlite3

import pytest
from fastapi.testclient import TestClient

from projects.p05_self_healing_pipeline.store import Store
from projects.p09_docker_agent.healthcheck import status
from projects.p09_docker_agent.native import DockerError, package_inputs
from projects.p09_docker_agent.relay import create_relay


def test_readiness_checks_real_sqlite_and_required_model(tmp_path):
    database = tmp_path / 'audit.sqlite3'
    models = [{'name': 'qwen3:4b'}]

    def fetch(url):
        if url.endswith('/health'):
            return {'contract': 'orders-v1'}
        return {'models': models}

    with pytest.raises(sqlite3.OperationalError):
        status(fetch, database, 'qwen3:4b')
    assert not database.exists()
    Store(database)
    assert status(fetch, database, 'qwen3:4b') is None
    models.clear()
    assert status(fetch, database, 'qwen3:4b') == 'The required local model is missing.'


def test_relay_forwards_only_expected_routes_and_media():
    calls = []

    def connector(*args):
        calls.append(args)
        return (b'HTTP/1.1 409 Conflict\r\nContent-Type: application/json\r\n'
                b'Cache-Control: no-store\r\nSet-Cookie: remote=value\r\n\r\n{"detail":"stale"}')

    with TestClient(create_relay(connector=connector), base_url='http://127.0.0.1:8109') as client:
        response = client.post('/api/rollback', json={}, headers={'Origin': 'http://127.0.0.1:8109'})
        assert response.status_code == 409 and response.json() == {'detail': 'stale'}
        assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
        assert client.post('/api/ingest', json={}, headers={'Origin': 'http://outside.test'}).status_code == 403
        assert client.post('/api/ingest', content='not JSON').status_code == 415
        assert client.post('/api/ingest', json={'csv_text': 'x' * 65000}).status_code == 413
        assert client.get('/api/models?proxy=other').status_code == 404
        assert client.get('/api/batches/escape').status_code == 404
        assert client.get('/health', headers={'Host': 'outside.test'}).status_code == 400
    assert calls == [('genai-portfolio-docker', 'POST', '/api/rollback', b'{}')]


def test_relay_sanitizes_upstream_failures():
    def unavailable(*args):
        raise DockerError('internal socket path')

    for connector in (unavailable, lambda *args: b'malformed'):
        with TestClient(create_relay(connector=connector), base_url='http://localhost:8109') as client:
            response = client.get('/health')
            assert response.status_code == 503
            assert response.json() == {'detail': 'The local Compose service is unavailable.'}


def test_build_context_contains_only_required_local_app_inputs():
    names = dict(package_inputs())
    assert 'projects/p05_self_healing_pipeline/data/drifted.csv' in names
    assert 'projects/p05_self_healing_pipeline/static/index.html' in names
    assert 'projects/p09_docker_agent/compose.yaml' in names
    assert 'projects/p09_docker_agent/requirements-linux.txt' in names
    assert len(names) == 22
    assert all('.env' not in name and '.runtime' not in name and '__pycache__' not in name for name in names)
