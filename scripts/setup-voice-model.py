"""Fetch only the pinned public English STT weights into the portfolio."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.p02_voice_agent.config import MODEL_FILES, MODEL_ID, MODEL_PATH, MODEL_REVISION


def main():
    cache = ROOT / '.cache' / 'voice-huggingface'
    os.environ.update({
        'HF_HOME': str(cache), 'HF_HUB_CACHE': str(cache / 'hub'), 'HF_XET_CACHE': str(cache / 'xet'),
        'HF_HUB_DISABLE_XET': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
    })
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=MODEL_PATH,
                      allow_patterns=MODEL_FILES, token=False)
    model = MODEL_PATH / 'model.bin'
    with model.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    print(json.dumps({'model': MODEL_ID, 'revision': MODEL_REVISION, 'model_bytes': model.stat().st_size,
                      'model_sha256': digest, 'directory': str(MODEL_PATH)}, indent=2))


if __name__ == '__main__':
    main()
