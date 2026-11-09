"""Verify a fresh Compose stack, live repair and durable audit data on D:."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
from time import perf_counter, sleep
from uuid import uuid4

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.p09_docker_agent.native import Compose, build_image, docker, guest, stage_context
from projects.p09_docker_agent.relay import create_relay


def inspect(compose):
    container = compose.call('ps', '--quiet', 'agent').stdout.decode().strip()
    instance = json.loads(docker('inspect', container).stdout)[0]
    host = instance['HostConfig']
    assert instance['State']['Health']['Status'] == 'healthy'
    assert instance['Config']['User'] == '10001:10001' and '/tmp/clearflow.sock' in instance['Config']['Cmd']
    assert host['NetworkMode'] == 'host' and not host['PortBindings'] and host['ReadonlyRootfs']
    assert not host['Privileged'] and host['CapDrop'] == ['ALL']
    mount, = instance['Mounts']
    assert mount['Type'] == 'volume' and mount['Destination'] == '/app/.runtime' and mount['RW']
    assert mount['Name'] == compose.project + '_audit' and mount['Source'].startswith('/var/lib/docker/volumes/')
    return instance['Id'], mount['Name'], instance['State']['Health']['Status']


def read(client, path):
    return client.get(path).raise_for_status().json()


def ingest(client, source, model):
    start = perf_counter()
    response = client.post('/api/ingest', json={'csv_text': source, 'model': model})
    result = response.raise_for_status().json()
    print('Ingest:', result['status'], result.get('plan_origin'), result['model_calls_this_request'], flush=True)
    return {'http_status': response.status_code, 'http_elapsed_ms': round((perf_counter() - start) * 1000),
            'result': result}


def main():
    context, local, digest = stage_context()
    image = build_image(local, digest)
    assert image['Config']['Labels']['portfolio.context'] == digest
    compose = Compose(context, project='genai-portfolio-docker-qa-' + uuid4().hex[:8])
    configuration = json.loads(compose.call('config', '--format', 'json').stdout)
    assert configuration['services']['agent']['build']['context'] == context
    print('QA project:', compose.project, 'image:', image['Id'], flush=True)
    listen = socket.socket()
    listen.bind(('127.0.0.1', 0))
    base_url = f'http://127.0.0.1:{listen.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(create_relay(compose.project), log_level='error', proxy_headers=False))
    relay = Thread(target=server.run, kwargs={'sockets': [listen]}, daemon=True)
    try:
        start = perf_counter()
        compose.call('up', '--no-build', '--wait', '--wait-timeout', '70', timeout=85)
        first_ready_ms = round((perf_counter() - start) * 1000)
        first, volume, first_health = inspect(compose)
        missing = compose.call('exec', '-T', '-e', 'PIPELINE_MODEL=portfolio-missing-model', 'agent',
                               'python', '-m', 'projects.p09_docker_agent.healthcheck', check=False)
        assert missing.returncode == 1 and b'The required local model is missing.' in missing.stdout
        relay.start()
        for _ in range(50):
            if server.started:
                break
            sleep(0.1)
        assert server.started, 'Windows loopback relay failed to start.'
        with httpx.Client(base_url=base_url, timeout=215, trust_env=False) as client:
            assert read(client, '/health')['contract'] == 'orders-v1'
            assert read(client, '/api/snapshot')['active_revision'] == 0
            assert not read(client, '/api/history')['batches']
            samples = read(client, '/api/config')['samples']
            baseline = ingest(client, samples['baseline'], compose.model)
            repaired = ingest(client, samples['drifted'], compose.model)
            result = repaired['result']
            assert baseline['result']['status'] == 'committed' and baseline['result']['model_calls_this_request'] == 0
            assert result['status'] == 'committed' and result['plan_origin'] == 'model'
            assert 1 <= result['model_calls_this_request'] <= 2 and result['after']['valid_rows'] == 2
            repeat = ingest(client, samples['drifted'], compose.model)
            assert repeat['result']['idempotent_replay'] and repeat['result']['model_calls_this_request'] == 0
            snapshot = read(client, '/api/snapshot')
            batch_url = '/api/batches/' + result['batch_id']
            batch = read(client, batch_url)
            assert snapshot['totals'] == {'orders': 4, 'units': 8, 'revenue_cents': 252485}
            assert batch['source_sha'] == hashlib.sha256(samples['drifted'].encode()).hexdigest()
            compose.call('down', timeout=50)
            assert docker('inspect', first, check=False).returncode != 0
            docker('volume', 'inspect', volume)
            start = perf_counter()
            compose.call('up', '--no-build', '--wait', '--wait-timeout', '70', timeout=85)
            second_ready_ms = round((perf_counter() - start) * 1000)
            second, new_volume, second_health = inspect(compose)
            assert first != second and volume == new_volume
            assert read(client, '/api/snapshot') == snapshot and read(client, batch_url) == batch
        browser = subprocess.run(['node', 'scripts/check-docker-agent-ui.cjs', base_url, result['batch_id']],
                                 cwd=ROOT, check=True, capture_output=True, timeout=75)
        browser_checks = json.loads(browser.stdout)
        data = {
            'complete': True, 'verified_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'native WSL Docker image build and real Compose with local CPU inference',
            'docker': json.loads(docker('version', '--format', '{{json .}}').stdout)['Server']['Version'],
            'compose': docker('compose', 'version', '--short').stdout.decode().strip(),
            'image': {'id': image['Id'], 'bytes': image['Size'], 'context_sha256': digest},
            'model': compose.model, 'project': compose.project,
            'first_start': {'container': first, 'health': first_health, 'elapsed_ms': first_ready_ms},
            'recreated': {'container': second, 'health': second_health, 'elapsed_ms': second_ready_ms},
            'missing_model_healthcheck': {'exit': missing.returncode, 'output': missing.stdout.decode().strip()},
            'audit_volume': {'name': volume, 'retained_after_down': True, 'snapshot_and_batch_unchanged': True,
                             'source_sha256': batch['source_sha']},
            'storage': guest('/bin/df', '-P', '/var/lib/docker').stdout.decode().strip(),
            'runtime': {'nonroot_uid_gid': '10001:10001', 'root_read_only': True, 'capabilities_dropped': 'ALL',
                        'published_ports': [], 'guest_socket': '/tmp/clearflow.sock', 'windows_bind': '127.0.0.1'},
            'baseline': baseline, 'repair': repaired, 'repeat': repeat, 'snapshot': snapshot,
            'browser': browser_checks,
        }
        (ROOT / 'docs/docker-agent-live.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')
        print('Healthy before and after recreation. Preserved volume:', volume, flush=True)
    except Exception:
        logs = compose.call('logs', '--no-color', check=False).stdout
        (ROOT / '.runtime/docker-agent-qa.log').write_bytes(logs)
        raise
    finally:
        if relay.is_alive():
            server.should_exit = True
            relay.join(timeout=8)
        listen.close()
        compose.call('down', timeout=50)


if __name__ == '__main__':
    main()
