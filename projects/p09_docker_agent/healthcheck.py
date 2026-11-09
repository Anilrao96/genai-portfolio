"""Check HTTP, read-only database access and the required local model."""
from contextlib import closing
from http.client import HTTPException
import json
import os
from pathlib import Path
import sqlite3
import sys
from .transport import request


def status(fetch, database, model):
    if fetch('/health').get('contract') != 'orders-v1':
        return 'Clearflow HTTP service is not ready.'
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
        if connection.execute('SELECT revision FROM active WHERE singleton=1').fetchone() is None:
            return 'The audit database has no active snapshot pointer.'
    models = fetch('/api/models').get('models', [])
    if model not in {item['name'] for item in models}:
        return 'The required local model is missing.'
    return None


def fetch(path):
    code, _, body = request('GET', path, timeout=2)
    if code != 200:
        raise ValueError(f'Unexpected HTTP status {code}.')
    return json.loads(body)


def main():
    try:
        problem = status(fetch, os.environ['PIPELINE_STATE_PATH'], os.environ['PIPELINE_MODEL'])
    except (OSError, HTTPException, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
        problem = 'The local HTTP, audit database or model dependency is unavailable.'
    print(problem or 'Clearflow, audit state and required local model are ready.')
    return int(problem is not None)


if __name__ == '__main__':
    sys.exit(main())
