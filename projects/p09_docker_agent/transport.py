"""Request the packaged service over its private Unix socket."""
from contextlib import closing
from http.client import HTTPConnection
import socket
import sys

SOCKET_PATH = '/tmp/clearflow.sock'
MAX_RESPONSE = 8_000_000
RESPONSE_HEADERS = {'content-type', 'cache-control', 'content-security-policy',
                    'referrer-policy', 'x-content-type-options'}


class UnixConnection(HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET_PATH)


def request(method, path, body=None, timeout=200):
    headers = {'Content-Type': 'application/json'} if body is not None else {}
    with closing(UnixConnection('127.0.0.1', timeout=timeout)) as connection:
        connection.request(method, path, body, headers)
        with connection.getresponse() as response:
            content = response.read(MAX_RESPONSE + 1)
            if len(content) > MAX_RESPONSE:
                raise ValueError('Clearflow response exceeds the relay limit.')
            headers = {key.lower(): value for key, value in response.getheaders() if key.lower() in RESPONSE_HEADERS}
            return response.status, headers, content


def main():
    method, path = sys.argv[1:]
    if method not in ('GET', 'POST') or not path.startswith('/'):
        raise ValueError('Invalid relay request.')
    body = sys.stdin.buffer.read(65001) if method == 'POST' else None
    if body is not None and len(body) > 65000:
        raise ValueError('Clearflow request exceeds the relay limit.')
    status, headers, content = request(method, path, body)
    header = '\r\n'.join([f'HTTP/1.1 {status}', *(f'{key}: {value}' for key, value in headers.items())])
    sys.stdout.buffer.write(header.encode('latin-1') + b'\r\n\r\n' + content)


if __name__ == '__main__':
    main()
