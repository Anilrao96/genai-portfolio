import hashlib
import json
from pathlib import Path
import re

from pydantic import BaseModel,ConfigDict,Field,field_validator

ROOT=Path(__file__).resolve().parents[2]
FILES={'backend.py','App.jsx'}
DEFAULT_MODEL = 'qwen2.5-coder:1.5b'


class AppSpec(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    title:str=Field(min_length=3,max_length=60)
    item_label:str=Field(min_length=2,max_length=24,pattern=r'^[A-Za-z][A-Za-z ]+$')
    brief:str=Field(min_length=10,max_length=600)
    @field_validator('title','item_label','brief',mode='before')
    @classmethod
    def printable(cls,value):
        if not isinstance(value,str):return value
        if any(ord(char)<32 or ord(char)==127 for char in value):raise ValueError('Use printable text.')
        return value.strip()


class Source(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    code:str=Field(min_length=20,max_length=12000)
    note:str=Field(min_length=1,max_length=300)
    @field_validator('code')
    @classmethod
    def bound_bytes(cls,value):
        if len(value.encode('utf8'))>16000:raise ValueError('Source exceeds sixteen thousand UTF-8 bytes.')
        if '\x00' in value:raise ValueError('NUL is not source text.')
        return value


API_CONTRACT='''Implement an in-memory item tracker. Define app=FastAPI() in backend.py.
Every decorated route must use async def. Sync routes need a worker thread and this container denies new threads.
Record shape: {"id": positive integer, "title": string, "done": boolean}. Start empty; IDs increase from 1.
GET /api/items -> status 200, JSON array of records in ID order.
POST /api/items with {"title": string} -> status 201, new record with done=false. Strip title. Refuse blank/whitespace and >80 chars with status 422.
PATCH /api/items/{id} with {"done": boolean} -> status 200, updated record. Missing ID -> 404. Reject non-booleans with 422.
DELETE /api/items/{id} -> status 204, no content. Missing ID -> 404.
Use @app.post('/api/items', status_code=201), StrictBool for done, and Response(status_code=204) for successful deletion.
Use Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] for title validation.
Use FastAPI, Pydantic and Python standard library only. No files, networks, subprocesses, threads, package installs or startup hooks.
No static files, CORS, server launch or HTML in the backend. The trusted host supplies the frontend and HTTP transport.
'''


class Workspace:
    def __init__(self,run_id,path=None):
        if not re.fullmatch('[0-9a-f]{32}',run_id):raise ValueError('Invalid workspace ID.')
        base=(Path(path) if path else ROOT/'.runtime/app-builder/workspaces').resolve()
        if not base.is_relative_to((ROOT/'.runtime').resolve()):raise ValueError('Workspace must stay in the portfolio runtime directory.')
        self.base=base
        self.path=base/run_id
        if self.path.is_symlink() or self.path.resolve().parent!=base:raise ValueError('Unsafe workspace directory.')
        self.path.mkdir(parents=True,exist_ok=True)

    def write(self,name,source):
        if name not in FILES:raise ValueError('Generated paths are restricted to backend.py and App.jsx.')
        Source(code=source,note='Workspace source validation.')
        target=self.path/name
        if self.path.resolve().parent!=self.base or target.is_symlink() or target.resolve().parent!=self.path.resolve():raise ValueError('Unsafe workspace target.')
        target.write_text(source,encoding='utf8',newline='\n')
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def manifest(self,spec):
        files={name:hashlib.sha256((self.path/name).read_bytes()).hexdigest() for name in sorted(FILES) if (self.path/name).is_file()}
        value={'spec':spec.model_dump(),'files':files,'execution':'OCI containers only; never import generated source on Windows'}
        (self.path/'manifest.json').write_text(json.dumps(value,indent=2),encoding='utf8',newline='\n')
        return value
