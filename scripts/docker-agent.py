"""Run the owned Compose stack and its Windows loopback relay."""
import argparse
from pathlib import Path
import sys

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.p09_docker_agent.native import (
    COMPOSE_VERSION, WINDOWS_PORT, Compose, DockerError, build_image, docker,
    install_plugin, stage_context, verify_session,
)
from projects.p09_docker_agent.relay import create_relay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop'])
    parser.add_argument('--port', type=int, default=WINDOWS_PORT)
    parser.add_argument('--ollama-port', type=int, default=11435)
    parser.add_argument('--model', default='qwen3:4b')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a Windows loopback port between 1024 and 65535.')
    verify_session()
    version = docker('compose', 'version', '--short', check=False)
    if version.returncode or version.stdout.decode().strip().lstrip('v') != COMPOSE_VERSION:
        install_plugin()
    context, local, digest = stage_context()
    compose = Compose(context, model=args.model, ollama_port=args.ollama_port)
    if args.action == 'stop':
        compose.call('down', timeout=50)
        print('Clearflow Compose stopped. Its audit volume was preserved.')
        return
    image = build_image(local, digest)
    compose.call('up', '--no-build', '--wait', '--wait-timeout', '70', timeout=85)
    print(f'Clearflow container is healthy ({image["Id"]}). Open http://127.0.0.1:{args.port}.', flush=True)
    uvicorn.run(create_relay(), host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    try:
        main()
    except (DockerError, ValueError) as error:
        raise SystemExit(str(error)) from error
