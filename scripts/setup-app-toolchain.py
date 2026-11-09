"""Build only the trusted allowlisted toolchain, never a generated Dockerfile or project."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from projects.p06_code_assistant.sandbox import command,verify_ready
from projects.p06_code_assistant.session import CLI,SESSION
from projects.p08_app_builder.runtime import INPUTS, context_hash

CONTEXT=ROOT/'projects/p08_app_builder/toolchain'


def main():
    verify_ready()
    digest=context_hash();marker=ROOT/'.runtime/app-toolchain.json'
    if marker.is_file():
        previous=json.loads(marker.read_text())
        if previous['context_sha256']==digest and command(['image','inspect',previous['image_id']],check=False).returncode==0:
            print('Trusted app toolchain already matches its pinned image.');return
    log=ROOT/'.runtime/app-toolchain-build.log'
    env={**os.environ,'TEMP':str(ROOT/'.runtime/temp'),'TMP':str(ROOT/'.runtime/temp')}
    with log.open('wb') as output:
        result=subprocess.run([str(CLI),'--session',SESSION,'build','--progress','plain','--label','portfolio.project=p08_toolchain',
            '-t','portfolio-app-toolchain:1',str(CONTEXT)],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise SystemExit('Trusted image build failed; read .runtime/app-toolchain-build.log.')
    data=json.loads(command(['image','inspect','portfolio-app-toolchain:1','--format','json']).stdout)[0]
    value={'image_id':data['Id'],'context_sha256':digest,'tag':'portfolio-app-toolchain:1','bytes':data['Size'],
           'trusted_inputs':list(INPUTS),'generated_sources_in_build_context':False}
    marker.write_text(json.dumps(value,indent=2),encoding='utf8',newline='\n');print(json.dumps(value,indent=2))


if __name__=='__main__':main()
