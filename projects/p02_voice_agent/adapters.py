"""Replaceable local STT and TTS adapters with cancellable subprocesses."""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig

from anyio import CancelScope

from .audio import VoiceError, read_wav, write_wav
from .config import DEFAULT_VOICE, MAX_SPEECH, MODEL_FILES, MODEL_PATH, ROOT


async def run_worker(command, payload, *, timeout, max_output, failure):
    temporary = ROOT / '.runtime' / 'temp'
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'TEMP': str(temporary), 'TMP': str(temporary),
           'HF_HOME': str(ROOT / '.cache' / 'voice-huggingface'), 'HF_HUB_OFFLINE': '1'}
    try:
        process = await asyncio.create_subprocess_exec(
            *command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except OSError as error:
        raise VoiceError(failure) from error
    try:
        async with asyncio.timeout(timeout):
            output, _ = await process.communicate(payload)
        if process.returncode or not output or len(output) > max_output:
            raise VoiceError(failure)
        return output
    except TimeoutError as error:
        raise VoiceError('The local speech stage timed out.') from error
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with CancelScope(shield=True):
                await process.communicate()


class WhisperSTT:
    name = 'Whisper tiny.en · CPU int8'

    def ready(self):
        return all((MODEL_PATH / name).is_file() for name in MODEL_FILES)

    async def transcribe(self, pcm):
        if not self.ready():
            raise VoiceError('Whisper weights are missing. Run scripts/Setup-Voice.ps1.')
        # Invoke the base interpreter directly, so cancellation kills the worker
        # itself rather than a Windows virtual environment launcher.
        bootstrap = "import runpy,sys;sys.path[:0]=sys.argv[1:3];runpy.run_module('projects.p02_voice_agent.whisper_worker',run_name='__main__')"
        command = [sys._base_executable, '-I', '-B', '-c', bootstrap, str(ROOT), sysconfig.get_path('purelib')]
        output = await run_worker(command, pcm, timeout=20, max_output=6000,
                                  failure='Local transcription failed. Check the Whisper setup and retry.')
        try:
            result = json.loads(output)
            if not isinstance(result, dict) or not isinstance(result.get('text'), str):
                raise ValueError('Invalid speech response.')
        except ValueError as error:
            raise VoiceError('Whisper returned an unreadable transcript.') from error
        return result


class WindowsSpeech:
    def __init__(self, name=DEFAULT_VOICE):
        self.name = name
        self.shell = Path(os.getenv('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.script = ROOT / 'scripts' / 'Speak-Voice.ps1'

    def ready(self):
        return os.name == 'nt' and self.shell.is_file() and self.script.is_file()

    async def synthesize(self, text):
        if not self.ready():
            raise VoiceError('Windows local speech is unavailable on this machine.')
        if not 1 <= len(text) <= 500:
            raise VoiceError('The reply exceeds the local speech limit.')
        output = await run_worker([str(self.shell), '-NoProfile', '-NonInteractive', '-File', str(self.script),
                                   '-VoiceName', self.name], text.encode(), timeout=14, max_output=MAX_SPEECH,
                                  failure='Local speech failed. Check the installed Windows desktop voice.')
        if len(output) % 2:
            raise VoiceError('The local speech response is incomplete.')
        wav = write_wav(output)
        read_wav(wav, seconds=60)
        return wav
