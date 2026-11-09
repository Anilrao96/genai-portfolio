. "$PSScriptRoot\Use-Environment.ps1"
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Voice dependency setup failed.' }
uv run --frozen python scripts/setup-voice-model.py
if ($LASTEXITCODE -ne 0) { throw 'Whisper model setup failed.' }
