import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


class RunStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else ROOT/'.runtime/code-assistant/runs'
        self.path=self.path.resolve()
        if not self.path.is_relative_to(ROOT/'.runtime'):raise ValueError('Run storage must stay inside the portfolio runtime directory.')
        self.path.mkdir(parents=True,exist_ok=True)

    def save(self,run):
        if not re.fullmatch('[0-9a-f]{32}',run['id']):raise ValueError('Invalid run ID.')
        target=self.path/(run['id']+'.json')
        if not target.exists() and len(list(self.path.glob('*.json')))>=500:raise ValueError('Local run storage is limited to five hundred records.')
        temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(run,indent=2),encoding='utf8',newline='\n');temp.replace(target)

    def get(self,run_id):
        if not re.fullmatch('[0-9a-f]{32}',run_id):raise ValueError('Run not found.')
        path=self.path/(run_id+'.json')
        if not path.is_file():raise ValueError('Run not found.')
        return json.loads(path.read_text(encoding='utf8'))

    def history(self):
        paths=sorted(self.path.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]
        rows=[]
        for path in paths:
            r=json.loads(path.read_text(encoding='utf8'))
            rows.append({k:r[k] for k in ('id','task_id','status','model','model_calls','executions','created_at')})
        return rows
