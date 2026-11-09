import json

import pytest
from pydantic import ValidationError

from projects.p08_app_builder.contracts import AppSpec,Source,Workspace
from projects.p08_app_builder.runtime import LIMITS,MEMORY,IsolationError,inspect_policy


def spec():return AppSpec(title='Reading Room',item_label='book',brief='Track fictional books to read and mark them finished.')


def inspected():
    return {'Image':'sha256:'+'a'*64,'Config':{'User':'65534:65534','Labels':{'portfolio.project':'p08_app_builder'},
        'Healthcheck':{'Test':['NONE']},'Entrypoint':['python','-I','-B','/opt/builder/runner.py']},
        'HostConfig':{'NetworkMode':'none','Memory':MEMORY,'NanoCpus':500_000_000,
            'Ulimits':[{'Name':k,'Soft':v,'Hard':v} for k,v in LIMITS.items()]},'Mounts':[],'Ports':{}}


@pytest.mark.parametrize('change',['network','memory','user','mount','image','limits','labels','health','ports','entrypoint'])
def test_app_container_policy_refuses_weakened_boundary(change):
    data=inspected()
    if change=='network':data['HostConfig']['NetworkMode']='bridge'
    elif change=='memory':data['HostConfig']['Memory']=0
    elif change=='user':data['Config']['User']='0'
    elif change=='mount':data['Mounts']=[{'Source':'D:/'}]
    elif change=='image':data['Image']='sha256:'+'b'*64
    elif change=='limits':data['HostConfig']['Ulimits']=[]
    elif change=='labels':data['Config']['Labels']={}
    elif change=='health':data['Config']['Healthcheck']={'Test':['CMD','curl']}
    elif change=='entrypoint':data['Config']['Entrypoint']=['sh']
    else:data['Ports']={'80/tcp':[{'HostPort':'80'}]}
    with pytest.raises(IsolationError):inspect_policy(data,'sha256:'+'a'*64)


def test_source_paths_remain_two_fixed_files_and_manifest_tracks_content(tmp_path):
    workspace=Workspace('a'*32,tmp_path/'workspaces')
    code='from fastapi import FastAPI\napp=FastAPI()'
    digest=workspace.write('backend.py',code)
    assert workspace.manifest(spec())['files']=={'backend.py':digest}
    assert (workspace.path/'backend.py').read_text()==code
    for path in ('../elsewhere.py','/root/file','Dockerfile','package.json','..\\elsewhere.py'):
        with pytest.raises(ValueError):workspace.write(path,code)
    with pytest.raises(ValueError):Workspace('../outside',tmp_path)
    with pytest.raises(ValueError):Workspace('a'*32,'D:/outside-app-workspace')


@pytest.mark.parametrize('extra',[{'title':'x'},{'item_label':'<book>'},{'brief':'a\nb longer brief'},{'extra':1}])
def test_spec_bounds_and_plain_text(extra):
    with pytest.raises(ValidationError):AppSpec.model_validate({**spec().model_dump(),**extra})


def test_source_is_bounded_text_without_host_execution():
    with pytest.raises(ValidationError):Source(code='🌲'*5000,note='Bounded bytes.')
    with pytest.raises(ValidationError):Source(code='x'*50+'\x00',note='No NUL.')
    candidate=Source(code="raise RuntimeError('never execute on host')",note='Offline text only.')
    assert 'RuntimeError' in candidate.code
