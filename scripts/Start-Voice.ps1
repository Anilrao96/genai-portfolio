. "$PSScriptRoot\Use-Environment.ps1"
uv run --frozen uvicorn projects.p02_voice_agent.app:app --host 127.0.0.1 --port 8102
if ($LASTEXITCODE -ne 0) { throw 'Voice agent service failed.' }
