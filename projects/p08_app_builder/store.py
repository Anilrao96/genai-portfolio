import json
from pathlib import Path
import re

from .contracts import ROOT,Workspace


class BuildStore:
    def __init__(self,path=None):
        self.path=(Path(path) if path else ROOT/'.runtime/app-builder').resolve()
        if not self.path.is_relative_to((ROOT/'.runtime').resolve()):raise ValueError('Builder state must stay under portfolio runtime.')
        self.records=self.path/'runs';self.records.mkdir(parents=True,exist_ok=True)

    def workspace(self,run_id):return Workspace(run_id,self.path/'workspaces')

    def save(self,run):
        if not re.fullmatch('[0-9a-f]{32}',run['id']):raise ValueError('Invalid build ID.')
        target=self.records/(run['id']+'.json')
        if not target.exists() and len(list(self.records.glob('*.json')))>=100:raise ValueError('The local builder holds at most one hundred builds.')
        temp=target.with_suffix('.tmp');temp.write_text(json.dumps(run,indent=2),encoding='utf8',newline='\n');temp.replace(target)

    def get(self,run_id):
        if not re.fullmatch('[0-9a-f]{32}',run_id):raise ValueError('Build not found.')
        path=self.records/(run_id+'.json')
        if not path.is_file():raise ValueError('Build not found.')
        return json.loads(path.read_text(encoding='utf8'))

    def history(self):
        paths=sorted(self.records.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
        return [{key:run[key] for key in ('id','spec','model','status','model_calls','build_attempts')} for run in
            (json.loads(path.read_text(encoding='utf8')) for path in paths)]
