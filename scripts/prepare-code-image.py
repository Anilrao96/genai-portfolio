"""Pull a public official Python image, then pin its actual immutable local ID."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from projects.p06_code_assistant.sandbox import command,IMAGE_FILE
from projects.p06_code_assistant.session import STORAGE


def main():
    command(['system','session','run','/bin/true'])
    if not (STORAGE/'storage.vhdx').is_file():raise ValueError('No verified D: storage; refusing to pull an image.')
    tag='docker.io/library/python:3.13-alpine'
    command(['pull',tag],timeout=180)
    data=json.loads(command(['image','inspect',tag,'--format','json']).stdout)[0]
    value={'source':tag,'image_id':data['Id'],'repo_digests':data['RepoDigests'],
           'image_environment':data['Config']['Env'],'bytes':data['Size'],'storage_path':str(STORAGE)}
    IMAGE_FILE.write_text(json.dumps(value,indent=2),encoding='utf8')
    print(json.dumps(value,indent=2))


if __name__=='__main__':main()
