"""Start a project-owned native container session, without user-wide settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from projects.p06_code_assistant.session import CLI,READY,SESSION,STORAGE


def main():
    env={**os.environ,'TEMP':str(ROOT/'.runtime/temp'),'TMP':str(ROOT/'.runtime/temp')}
    check=subprocess.run([str(CLI),'system','session','list','--verbose'],capture_output=True,timeout=15,env=env)
    if SESSION in check.stdout.decode('utf8',errors='replace'):
        if not READY.is_file() or json.loads(READY.read_text())['storage_path']!=str(STORAGE):
            raise SystemExit('Session name collision; preserving the existing session.')
        print('Project session already active.');return
    if READY.exists():READY.unlink()
    with (ROOT/'.runtime/wslc-code.out.log').open('wb') as out,(ROOT/'.runtime/wslc-code.err.log').open('wb') as err:
        process=subprocess.Popen([sys.executable,'-m','projects.p06_code_assistant.session'],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(60):
        if process.poll() is not None:raise SystemExit('Session failed. Read .runtime/wslc-code.err.log; no unrestricted fallback is available.')
        if READY.is_file():print(READY.read_text());return
        time.sleep(0.5)
    raise SystemExit('Session startup exceeded thirty seconds. Inspect logs before retrying.')


if __name__=='__main__':main()
