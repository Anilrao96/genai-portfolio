"""Use the owned D-backed native WSL Docker Engine from Windows."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request

from projects.p06_code_assistant.session import CLI, READY, ROOT, SESSION, STORAGE

COMPOSE_VERSION = '5.6.0'
COMPOSE_SHA256 = '40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a'
COMPOSE_BYTES = 32663526
COMPOSE_URL = f'https://github.com/docker/compose/releases/download/v{COMPOSE_VERSION}/docker-compose-linux-x86_64'
GUEST_ROOT = '/var/lib/docker/genai-portfolio-compose'
GUEST_CONFIG = GUEST_ROOT + '/cli'
COMPOSE_FILE = 'projects/p09_docker_agent/compose.yaml'
COMPOSE_PROJECT = 'genai-portfolio-docker'
WINDOWS_PORT = 8109
PACKAGE_FILES = (
    'portfolio_core/__init__.py', 'portfolio_core/ollama.py', 'portfolio_core/structured.py',
    'projects/__init__.py', 'projects/p09_docker_agent/Dockerfile',
    'projects/p09_docker_agent/Dockerfile.dockerignore', COMPOSE_FILE,
    'projects/p09_docker_agent/requirements-linux.txt', 'projects/p09_docker_agent/healthcheck.py',
    'projects/p09_docker_agent/__init__.py', 'projects/p09_docker_agent/transport.py',
    *(f'projects/p05_self_healing_pipeline/{name}' for name in (
        '__init__.py', 'app.py', 'contract.py', 'engine.py', 'store.py',
        'data/baseline.csv', 'data/drifted.csv', 'data/quarantine.csv',
        'static/app.js', 'static/index.html', 'static/style.css',
    )),
)
IMAGE = 'genai-portfolio-clearflow:1'


class DockerError(RuntimeError):
    pass


def invoke(args, *, payload=b'', timeout=30, check=True):
    temp = ROOT / '.runtime' / 'temp'
    temp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'TEMP': str(temp), 'TMP': str(temp)}
    try:
        result = subprocess.run([str(CLI), *args], input=payload, capture_output=True, cwd=ROOT, env=env,
                                timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DockerError('Native Docker command failed to start or exceeded its deadline.') from error
    if check and result.returncode:
        message = (result.stderr or result.stdout).decode('utf8', errors='replace').strip()
        raise DockerError(message[-1800:] or 'Native Docker command failed.')
    return result


def guest(*args, **options):
    return invoke(['--session', SESSION, 'system', 'session', 'run', *args], **options)


def verify_session():
    try:
        state = json.loads(READY.read_text(encoding='utf8'))
        if state['session'] != SESSION or Path(state['storage_path']).resolve() != STORAGE.resolve():
            raise ValueError('Session configuration mismatch.')
        owner = int(state['creator_pid'])
        listing = invoke(['system', 'session', 'list', '--verbose']).stdout.decode()
        if not re.search(rf'^\d+\s+{owner}\s+{re.escape(SESSION)}\s*$', listing, re.MULTILINE):
            raise ValueError('Owned session is not running.')
        guest('/bin/true')
        if not (STORAGE / 'storage.vhdx').is_file() or not STORAGE.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('D-backed Docker storage is missing.')
    except (OSError, KeyError, ValueError) as error:
        raise DockerError('Start the owned portfolio WSL session before running Compose.') from error
    return state


def docker(*args, **options):
    return guest('/bin/env', '-u', 'DOCKER_HOST', '-u', 'DOCKER_CONTEXT',
                 f'DOCKER_CONFIG={GUEST_CONFIG}', 'DOCKER_API_VERSION=1.44', 'COMPOSE_BAKE=false',
                 '/bin/docker', '-H', 'unix:///var/run/docker.sock', *args, **options)


def install_plugin():
    verify_session()
    cache = ROOT / '.cache' / 'downloads' / f'docker-compose-{COMPOSE_VERSION}-linux-x86_64'
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        with urllib.request.urlopen(COMPOSE_URL, timeout=45) as response:
            downloaded = response.read(COMPOSE_BYTES + 1)
        if len(downloaded) != COMPOSE_BYTES or hashlib.sha256(downloaded).hexdigest() != COMPOSE_SHA256:
            raise DockerError('Downloaded Compose plugin did not match the published digest.')
        cache.write_bytes(downloaded)
    data = cache.read_bytes()
    if len(data) != COMPOSE_BYTES or hashlib.sha256(data).hexdigest() != COMPOSE_SHA256:
        raise DockerError('Cached Compose plugin digest mismatch. Preserve the file and review it.')
    plugin_dir = GUEST_CONFIG + '/cli-plugins'
    install = '''set -eu
mkdir -p "$1"
cat > "$1/docker-compose.new"
printf '%s  %s\\n' "$2" "$1/docker-compose.new" | sha256sum -c -
chmod 755 "$1/docker-compose.new"
mv "$1/docker-compose.new" "$1/docker-compose"
'''
    guest('/bin/sh', '-c', install, 'install-compose', plugin_dir, COMPOSE_SHA256, payload=data, timeout=120)
    version = docker('compose', 'version', '--short').stdout.decode().strip()
    if version.lstrip('v') != COMPOSE_VERSION:
        raise DockerError('The installed Compose plugin reported an unexpected version.')
    return version


def package_inputs():
    for filename in sorted(PACKAGE_FILES):
        path = ROOT / filename
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise DockerError('Build context contains a linked or out-of-scope file.')
        yield filename, path.read_bytes()


def stage_context():
    verify_session()
    archive = io.BytesIO()
    files = dict(package_inputs())
    with tarfile.open(fileobj=archive, mode='w') as bundle:
        for filename, payload in files.items():
            member = tarfile.TarInfo(filename)
            member.size = len(payload)
            member.mode = 0o644
            bundle.addfile(member, io.BytesIO(payload))
    payload = archive.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    target = GUEST_ROOT + '/source/' + digest
    guest('/bin/sh', '-c', 'mkdir -p "$1" && tar -xf - -C "$1"', 'stage-compose', target, payload=payload)
    local = ROOT / '.runtime' / 'p09-build' / digest
    for filename, data in files.items():
        path = local / filename
        if not path.resolve().is_relative_to(local.resolve()) or not local.resolve().is_relative_to(ROOT.resolve()):
            raise DockerError('Staged build context escapes the portfolio directory.')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return target, local, digest


def build_image(local, digest):
    previous = docker('image', 'inspect', IMAGE, check=False)
    if previous.returncode == 0:
        image = json.loads(previous.stdout)[0]
        if (image['Config'].get('Labels') or {}).get('portfolio.context') == digest:
            return image
    dockerfile = local / 'projects/p09_docker_agent/Dockerfile'
    result = invoke(['--session', SESSION, 'build', '--progress', 'plain', '--label',
                     f'portfolio.context={digest}', '-f', str(dockerfile), '-t', IMAGE, str(local)],
                    timeout=600, check=False)
    (ROOT / '.runtime/docker-agent-build.log').write_bytes(result.stdout + b'\n' + result.stderr)
    if result.returncode:
        raise DockerError('Image build failed. Read .runtime/docker-agent-build.log.')
    return json.loads(docker('image', 'inspect', IMAGE).stdout)[0]


class Compose:
    def __init__(self, context, project=COMPOSE_PROJECT, model='qwen3:4b', ollama_port=11435):
        if not re.fullmatch(r'genai-portfolio-docker(?:-qa-[0-9a-f]{8})?', project):
            raise ValueError('Use a portfolio-owned Compose project name.')
        if not 1024 <= ollama_port <= 65535:
            raise ValueError('Invalid loopback port.')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,119}', model):
            raise ValueError('Invalid local model name.')
        self.context = context
        self.project = project
        self.model = model
        self.ollama_port = ollama_port

    def call(self, *args, **options):
        return guest('/bin/env', '-u', 'DOCKER_HOST', '-u', 'DOCKER_CONTEXT',
                     f'DOCKER_CONFIG={GUEST_CONFIG}', 'DOCKER_API_VERSION=1.44', 'COMPOSE_BAKE=false',
                     f'PIPELINE_MODEL={self.model}',
                     f'PIPELINE_OLLAMA_PORT={self.ollama_port}',
                     '/bin/docker', '-H', 'unix:///var/run/docker.sock', 'compose',
                     '--project-name', self.project,
                     '-f', f'{self.context}/{COMPOSE_FILE}', *args, **options)
