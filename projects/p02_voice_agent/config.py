from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = 'Systran/faster-whisper-tiny.en'
MODEL_REVISION = '0d3d19a32d3338f10357c0889762bd8d64bbdeba'
MODEL_PATH = ROOT / '.models' / 'voice-whisper-tiny.en'
MODEL_FILES = ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt')
SAMPLE_RATE = 16000
MAX_SECONDS = 12
MAX_INPUT = SAMPLE_RATE * MAX_SECONDS * 2 + 4096
MAX_SPEECH = 2_000_000
DEFAULT_CHAT = 'qwen2.5:1.5b'
DEFAULT_VOICE = 'Microsoft Zira Desktop'
