"""Project-local official NuGet SDK pinned to the installed WSL 3.0.3 API."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='3.0.3'
SHA256='95a1e606bc15f363f85128b19a6befcda0e4aaf770fc6b4ba2004ef275a03f1b'
URL=f'https://api.nuget.org/v3-flatcontainer/microsoft.wsl.containers/{VERSION}/microsoft.wsl.containers.{VERSION}.nupkg'


def main():
    archive=ROOT/'.cache/downloads'/f'microsoft.wsl.containers.{VERSION}.nupkg'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=30) as response:payload=response.read(10_000_001)
        if len(payload)>10_000_000 or hashlib.sha256(payload).hexdigest()!=SHA256:raise ValueError('SDK checksum/size mismatch.')
        archive.write_bytes(payload)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:raise ValueError('Cached SDK checksum mismatch.')
    dest=ROOT/'.tools/wslc-sdk';dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for name in ('include/wslcsdk.h','runtimes/win-x64/native/wslcsdk.dll'):
            target=dest/Path(name).name;content=package.read(name)
            if target.exists():
                if target.read_bytes()!=content:raise ValueError('Existing SDK file changed; preserving it.')
                continue
            target.write_bytes(content)
    print(json.dumps({'sdk':VERSION,'path':str(dest),'sha256':SHA256}))


if __name__=='__main__':main()
