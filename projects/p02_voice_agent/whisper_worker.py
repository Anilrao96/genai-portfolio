"""One cancellable CPU transcription process per turn."""
import json
import sys
from time import perf_counter

from .config import MAX_SECONDS, MODEL_PATH, SAMPLE_RATE


def main():
    import numpy as np
    from faster_whisper import WhisperModel

    max_pcm = SAMPLE_RATE * MAX_SECONDS * 2
    pcm = sys.stdin.buffer.read(max_pcm + 1)
    if not pcm or len(pcm) > max_pcm or len(pcm) % 2:
        raise ValueError('Invalid PCM length.')
    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    start = perf_counter()
    model = WhisperModel(str(MODEL_PATH), device='cpu', compute_type='int8', cpu_threads=4,
                         num_workers=1, local_files_only=True)
    loaded = perf_counter()
    segments, _ = model.transcribe(samples, language='en', beam_size=1, temperature=0,
                                   condition_on_previous_text=False, vad_filter=True, max_new_tokens=128)
    text = ' '.join(segment.text.strip() for segment in segments).strip()
    print(json.dumps({'text': text[:700], 'model_load_ms': round((loaded - start) * 1000),
                      'decode_ms': round((perf_counter() - loaded) * 1000)}))


if __name__ == '__main__':
    main()
