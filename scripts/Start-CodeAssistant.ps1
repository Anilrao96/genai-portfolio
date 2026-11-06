. "$PSScriptRoot\Use-Environment.ps1"
uv run --frozen python scripts/start-code-session.py
if ($LASTEXITCODE -ne 0) { throw 'Run Setup-CodeAssistant.ps1 before starting the code assistant.' }
uv run --frozen python scripts/probe-code-isolation.py --ensure
if ($LASTEXITCODE -ne 0) { throw 'Isolation checks failed; candidate execution is disabled.' }
$CodePort=if ($env:CODE_PORT) { [int]$env:CODE_PORT } else { 8106 }
uv run --frozen uvicorn projects.p06_code_assistant.app:app --host 127.0.0.1 --port $CodePort
if ($LASTEXITCODE -ne 0) { throw 'Code assistant service failed.' }
